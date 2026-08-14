from . import jsonio, paths, pp3, provenance, recipe, render

_WB_KEYS = ("Setting", "Temperature", "Green")
_CONTROLS = {
    "wb": ("White Balance", _WB_KEYS),
    "exposure": ("Exposure", ("Compensation",)),
}


def _load_recipe(stem):
    try:
        return recipe.load(stem)
    except FileNotFoundError as error:
        raise jsonio.CommandError("NOT_FOUND", f"unknown stem: {stem}") from error


def _validate(style, temperature, exposure, reset):
    if style not in paths.STYLES:
        raise jsonio.CommandError("BAD_INPUT", f"unknown style: {style}")
    if reset and (temperature is not None or exposure is not None):
        raise jsonio.CommandError("BAD_INPUT", "--reset takes no values")
    if not reset and temperature is None and exposure is None:
        raise jsonio.CommandError("BAD_INPUT", "nothing to adjust")
    if temperature is not None and not 3000 <= int(temperature) <= 9000:
        raise jsonio.CommandError("BAD_INPUT", "temperature out of range 3000-9000")
    if exposure is not None and not -1.0 <= float(exposure) <= 1.0:
        raise jsonio.CommandError("BAD_INPUT", "exposure out of range -1.0..1.0")


def _capture_previous(doc, section, keys):
    return {k: doc.get(section, k) for k in keys}


def _own(rec, style):
    return rec.setdefault("app_adjustments", {}).setdefault(style, {})


def _reconcile(rec, style, doc):
    """Drop ownership of any bundle whose current pp3 values diverged from
    last_written (a hand edit — or a crash between sidecar and recipe writes
    — happened since the app wrote). Runs before EVERY operation, so a later
    app write re-captures `previous` from the hand-edited state instead of
    silently overwriting it, and reset can never touch a diverged bundle.
    Returns True if any ownership entry was dropped (recipe needs saving)."""
    dropped = False
    ownership = (rec.get("app_adjustments") or {}).get(style) or {}
    for control in list(ownership):
        section, keys = _CONTROLS[control]
        current = _capture_previous(doc, section, keys)
        if current != ownership[control].get("last_written"):
            del rec["app_adjustments"][style][control]
            dropped = True
    return dropped


def _write_control(rec, style, doc, control, values):
    section, keys = _CONTROLS[control]
    ownership = _own(rec, style)
    if control not in ownership:
        ownership[control] = {"previous": _capture_previous(doc, section, keys)}
    for key in keys:
        doc.set(section, key, values[key])
    ownership[control]["last_written"] = dict(values)


def _reset_control(rec, style, doc, control):
    # _reconcile already removed diverged bundles; anything still owned is
    # exactly as the app last wrote it and is safe to restore.
    section, keys = _CONTROLS[control]
    entry = _own(rec, style).get(control)
    if entry is None:
        return False
    for key in keys:
        prior = entry["previous"].get(key)
        if prior is None:
            doc.remove(section, key)
        else:
            doc.set(section, key, prior)
    doc.remove_section_if_empty(section)   # no stranded [White Balance] headers
    del rec["app_adjustments"][style][control]
    return True


def _semantically_empty(doc):
    # Only a TRULY empty document qualifies — a comment-only sidecar (e.g.
    # from render.ensure_sidecar) is "something else remaining": deleting it
    # would change style_hashes (sidecar existence feeds the fingerprint).
    return doc.dump().strip() == ""


def preview_result(stem, style, revision_before):
    """The result body shared by `adjust` and `preview` — both report the
    preview they just produced plus the revision it moved from and to.
    Reads the recipe back from disk: a render records preview provenance."""
    from . import status as status_mod
    rec = recipe.load(stem)
    return {
        "stem": stem,
        "style": style,
        "preview": f"previews/{stem}_{style}_preview.jpg",
        "temperature": status_mod._control(stem, style, "White Balance",
                                           "Temperature", int),
        "exposure": status_mod._control(stem, style, "Exposure",
                                        "Compensation", float),
        "review_revision_before": revision_before,
        "review_revision_after": provenance.review_revision(stem, rec),
    }


def apply(stem, style, temperature=None, exposure=None, reset=False):
    _validate(style, temperature, exposure, reset)
    rec = _load_recipe(stem)
    revision_before = provenance.review_revision(stem, rec)
    side_path = paths.sidecars_dir() / f"{stem}_{style}.pp3"
    doc = pp3.Pp3.load(side_path)
    recipe_dirty = _reconcile(rec, style, doc)     # spec §4.2 crash reconcile
    sidecar_dirty = False
    if reset:
        for control in _CONTROLS:
            if _reset_control(rec, style, doc, control):
                sidecar_dirty = recipe_dirty = True
    else:
        if temperature is not None:
            _write_control(rec, style, doc, "wb", {
                "Setting": "Custom",
                "Temperature": str(int(temperature)),
                "Green": "1.0",
            })
            sidecar_dirty = recipe_dirty = True
        if exposure is not None:
            _write_control(rec, style, doc, "exposure",
                           {"Compensation": f"{float(exposure):g}"})
            sidecar_dirty = recipe_dirty = True
    if sidecar_dirty:
        if side_path.exists() and _semantically_empty(doc):
            side_path.unlink()           # spec: "and the file if nothing else remains"
        else:
            doc.write_atomic(side_path)  # sidecar first…
    if recipe_dirty:
        recipe.save(stem, rec)           # …recipe second (spec §4.2 crash rule)
    if sidecar_dirty:
        from . import driver
        try:
            driver.preview_photo(stem, style)
        except render.RenderError as error:
            raise jsonio.CommandError("RENDER_FAILED", str(error)) from error
    return preview_result(stem, style, revision_before)
