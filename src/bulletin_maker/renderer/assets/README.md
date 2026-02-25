# Notation Image Assets

Static notation images for ELW Setting Two liturgical music,
auto-downloaded from Sundays & Seasons Library.

## Auto-Download

These images are fetched automatically via `download_setting_assets()` in
`image_manager.py`. It uses the S&S Library `/File/GetImage?atomCode=` endpoint.

```python
from bulletin_maker.sns.client import SundaysClient
from bulletin_maker.renderer.image_manager import download_setting_assets

with SundaysClient() as client:
    download_setting_assets(client)
```

Re-running is safe — it skips files that already exist.

## Contents

### `setting_two/` — ELW Setting Two pieces (static, don't change weekly)

| File | Atom Code | Liturgical Piece |
|------|-----------|-----------------|
| `kyrie.jpg` | `elw_hc2_kyrie_m` | Kyrie eleison |
| `glory_to_god.jpg` | `elw_hc2_glory_m` | Glory to God |
| `this_is_the_feast.jpg` | `elw_hc2_feast_m` | This Is the Feast |
| `great_thanksgiving.jpg` | `elw_hc2_dialogue_m` | Great Thanksgiving dialog |
| `sanctus.jpg` | `elw_hc2_holy_m` | Holy, Holy, Holy (Sanctus) |
| `memorial_acclamation.jpg` | `elw_hc2_christ_m` | Memorial Acclamation |
| `agnus_dei.jpg` | `elw_hc2_lamb_m` | Lamb of God (Agnus Dei) |
| `nunc_dimittis.jpg` | `elw_hc2_nowlord_m` | Now, Lord (Nunc Dimittis) |
| `amen.jpg` | `elw_hc2_amen_m` | Amen |

### `gospel_acclamation/` — Seasonal Gospel Acclamation variants

| File | Atom Code | Season(s) |
|------|-----------|-----------|
| `alleluia.jpg` | `elw_hc2_accltext_m` | Ordinary Time, Epiphany, Easter |
| `lenten_verse.jpg` | `elw_hc2_lentaccl_m` | Lent ("Return to the Lord") |
| `advent.jpg` | `elw_hc2_accltext_m` | Advent (same melody as alleluia) |

## Notes

- S&S serves these as JPEG via the Library API
- The Gospel Acclamation is the **only** notation image in the Large Print document
- The standard bulletin will use all Setting Two images plus the communion hymn notation
