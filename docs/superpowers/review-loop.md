# Visual Review Loop (operator runbook)

Per photo, per style:
1. Read `previews/<stem>_<style>_preview.jpg` at full size.
2. Judge: exposure, white balance/skin tones, highlight retention, shadow
   detail, style intent (natural = faithful; filmic = subtly warm; bw =
   tonal separation on faces).
3. If adjustment needed, edit `sidecars/<stem>_<style>.pp3` (plain INI,
   layered over the base style). Common keys:
   `[Exposure] Compensation=0.15`
   `[White Balance] Setting=Custom / Temperature=5400 / Green=1.0`
   `[Shadows & Highlights] Enabled=true / Highlights=12 / Shadows=8`
   `[Vibrance] Pastels=8`
   `[Black & White] MixerRed=35` (bw only)
4. Re-run `scripts/process.sh preview <stem> <style>` and re-Read. Iterate
   until it holds up.
5. Style calibration must be judged against ALL frames of a delivery before
   any is approved — Checkpoint 1 found P1036170 (dusk overcast) materially
   cooler and flatter than P1036163 (golden hour); a style tuned only on 63
   leaves 70 dull. Per-image sidecars reconcile them.
6. Expression audit (mandatory — approval refuses an empty audit), once per
   photo on the natural preview: per person — eyes open? natural smile?
   looking at camera? Record findings in `recipes/<stem>.yaml` under
   `expression_audit` as strings ("subject 2nd from left: eyes half
   closed"; "all eleven subjects: eyes open, natural smiles"). When
   multiple frames of the same grouping exist in a delivery, add a ranking
   note to each recipe ("strongest frame of this grouping: <stem>").
7. Crop review BEFORE approval: run
   `scripts/process.sh croppreview <stem> <style> <crop>` for each crop and
   Read the result. If a default centered window clips heads/hands or puts
   content inside the 2% safe edge, write a corrected normalized window
   into `recipes/<stem>.yaml` under `crops:` (`{x, y, w, h}` as 0..1
   fractions of source), re-preview, only then approve.
8. When all three styles + crops hold up:
   `scripts/process.sh approve <stem>` then `scripts/process.sh run`
   (renders → verifies → publishes; only `verified` photos are complete).
9. If a photo ever gets manual Photoshop/Topaz work: save the raster to
   `archive/`, record `{file, sha256}` in the recipe's `manual_assets`,
   and note the photo is outside automated re-render from that point.
10. Commit the recipe + sidecars after each photo's approval.
