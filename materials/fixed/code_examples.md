# Code Examples

ソース素材から直接引用したコードスニペット。

---

## 1. 画像挿入時のZ-order保持（Visualizer）

PPTXに画像を挿入する際、`add_picture()` はデフォルトで最前面に追加されるため
KOLCover等で背面のカバー画像がKOL名やロゴを隠すバグが発生する。
以下の関数で元のZ-order位置を保持して挿入する。

```python
def insert_image_preserving_zorder(slide, shape, image_path):
    sp = shape._element
    parent = sp.getparent()
    idx = list(parent).index(sp)  # 元の Z-order 位置を記録
    left, top, width, height = shape.left, shape.top, shape.width, shape.height
    parent.remove(sp)
    pic = slide.shapes.add_picture(str(image_path), left, top, width, height)
    pic_elem = pic._element
    parent.remove(pic_elem)
    parent.insert(idx, pic_elem)  # 元の位置に戻す
```

---

## 2. endParaRPr 順序修正（Visualizer）

python-pptxでテキスト書き込み後、`a:endParaRPr` が `a:r` runより前に来ると
PowerPoint / Google Slidesがテキストを表示しないバグが発生する。
binding適用の最終ステップとして必ず実行する。

```python
from lxml import etree

nsmap = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape._element.findall('.//a:p', nsmap):
                endParaRPr = para.find('a:endParaRPr', nsmap)
                runs = para.findall('a:r', nsmap)
                if endParaRPr is not None and runs:
                    children = list(para)
                    epr_idx = children.index(endParaRPr)
                    last_run_idx = max(children.index(r) for r in runs)
                    if epr_idx < last_run_idx:
                        para.remove(endParaRPr)
                        para.append(endParaRPr)
```

---

## 3. ブランドカラーによるテキスト色の自動判定（Visualizer）

W3C相対輝度を使い、背景色（ブランドカラー）に対して可読性の高い文字色（白/黒）を自動判定する。

```python
def contrast_text_color(bg_hex: str) -> str:
    """W3C 相対輝度で可読テキスト色を判定"""
    bg = bg_hex.lstrip("#")
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "FFFFFF" if luminance < 0.5 else "030303"
```

---

## 4. ブランドカラーの薄め処理（Outline スライド対応）（Visualizer）

Outlineスライドではブランドカラーの濃色をそのまま使うと黒文字が読めなくなるため、
白方向に85%薄める。

```python
def lighten_color(hex_color, factor=0.85):
    """暗い色を白方向に薄める。factor=0.85 で約85%薄くする"""
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    r2 = int(r + (255 - r) * factor)
    g2 = int(g + (255 - g) * factor)
    b2 = int(b + (255 - b) * factor)
    return f"{r2:02X}{g2:02X}{b2:02X}"

for slide in prs.slides:
    is_outline = any("Outline" in s.name for s in slide.shapes)
    for shape in slide.shapes:
        if shape.name.endswith("_brand"):
            if shape.fill.type == 5:  # BACKGROUND: 透明背景はスキップ
                continue
            fill = shape.fill
            fill.solid()
            if is_outline:
                fill.fore_color.rgb = RgbColor.from_string(lighten_color(brand_color.lstrip("#")))
            else:
                fill.fore_color.rgb = RgbColor.from_string(brand_color.lstrip("#"))
```

---

## 5. Confidential shape のブランドカラー上書き（Visualizer）

`*_Confidential_fixed` という名前のShapeのfill（テーマ黒）をブランドカラーに上書きする。

```python
from pptx.dml.color import RgbColor
# brand_color は data_binding["brand_color"]["primary"] から取得（先頭 # を除く）
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.name.endswith("_Confidential_fixed"):
            fill = shape.fill
            fill.solid()
            fill.fore_color.rgb = RgbColor.from_string(brand_color.lstrip("#"))
```

---

## 6. KOLCover_KOLName の背景色を白に上書き（Visualizer）

```python
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.name == "KOLCover_KOLName":
            fill = shape.fill
            fill.solid()
            fill.fore_color.rgb = RgbColor.from_string("FFFFFF")
```

---

## 7. フォントサイズの明示設定（Visualizer）

テーマ継承サイズに依存するとテキストが枠からはみ出すため、全テキスト runに明示設定する。

```python
from pptx.util import Pt
for para in shape.text_frame.paragraphs:
    for run in para.runs:
        run.font.size = Pt(font_size_pt)
```

主なShapeごとのデフォルト値:

| Shape パターン | font_size_pt |
|---|---|
| `Creative_Script` / `Creative_Hook` / `Creative_ShotList` | 9 |
| `Creative_KeyMessage` / `Creative_Direction` | 9 |
| `Caption_*` 系 | 9 |
| `Caution_*` 系 | 10 |
| `KOLCover_KOLName` | 20 |

---

## 8. Overflow 自己修正スクリプト（Builder）

data_binding のテキストがスライドテンプレートの `max_len` を超えていないか確認する。
最大3回の iteration で修正する（情報削減は禁止、短い表現に書き直す）。

```bash
python3 scripts/utils/check_text_overflow.py \
  --data-binding {data_binding_path} \
  --template-dir templates/post_instructions \
  --output {overflow_report_path}
```

---

## 9. data_binding.json の画像エントリ形式（Builder 仕様）

```json
{
  "slides": [
    {
      "slide_type": "IGReelCreative",
      "data": {
        "Creative_HeroImage_img": {"asset_id": "kol_scene0_tanaka"},
        "Creative_MainVisual_img": {"asset_id": "kol_scene1_tanaka"},
        "Creative_Scene2_img": {"asset_id": "kol_scene2_tanaka"},
        "Creative_Scene3_img": {"asset_id": "kol_scene3_tanaka"},
        "Creative_Scene4_img": {"asset_id": "kol_scene4_tanaka"},
        "Creative_Scene5_img": {"visible": false, "text": ""},
        "Global_MasterLogo_img": {"asset_id": "client_logo"},
        "KOLCover_KOLName": {
          "text": "　　　　Instagram REEL  /  田中様",
          "font_size_pt": 20
        }
      }
    }
  ],
  "brand_color": {
    "primary": "#00A3C4",
    "light": "#E0F5FA"
  }
}
```

---

## 10. run_state.json の構造（Orchestrator）

```json
{
  "project": "{project}",
  "mode": "post-instructions",
  "execution_mode": "classic_small|thin_large",
  "status": "running|complete|escalated",
  "current_phase": "phase1|phase2|phase3|phase4|phase5|phase6|phase7|phase8",
  "run_id": "20240415T123456Z"
}
```

---

## 11. per_kol_packages.json の主要フィールド（Planner 出力）

```json
[
  {
    "kol_name": "田中花子",
    "kol_slug": "tanaka",
    "selected_platform": "instagram_reel",
    "selected_creative_type": "UGC",
    "render_medium": "semi_real_anime",
    "scene_count": 4,
    "visual_direction": {
      "color_tone": "ナチュラルウォーム",
      "lighting": "自然光",
      "mood": "等身大感",
      "background_style": "生活感のある空間",
      "avoid": "暗い背景・過度な加工"
    },
    "creative_direction": "毎日のスキンケアルーティンの中で商品を自然に使用するシーンを見せる",
    "caption_direction": "【必須訴求内容】\n日差しが強い季節でも素肌感を守りながらUVケア。\n\n【必須ワード】\nUV、スキンケア感覚、もっちりテクスチャー\n\n【NG表現】\n「完全に焼けない」「100%防御」等の過大表現",
    "caution_points": ["景品表示法・薬機法遵守", "効果効能の過大表現禁止", "#PR表示必須"],
    "reference_post_urls": ["https://www.instagram.com/p/example1/"]
  }
]
```
