import streamlit as st
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import io, base64, json, os, urllib.request
from pathlib import Path


def get_japanese_font(size: int):
    """macOS・Linux両対応の日本語フォントを返す"""
    mac_path = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
    if os.path.exists(mac_path):
        try:
            return ImageFont.truetype(mac_path, size)
        except Exception:
            pass
    font_cache = "/tmp/NotoSansJP.ttf"
    if not os.path.exists(font_cache):
        try:
            urllib.request.urlretrieve(
                "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf",
                font_cache,
            )
        except Exception:
            return ImageFont.load_default()
    try:
        return ImageFont.truetype(font_cache, size)
    except Exception:
        return ImageFont.load_default()

st.set_page_config(page_title="四コマ漫画メーカー", page_icon="📖", layout="wide")
st.title("📖 四コマ漫画メーカー")

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input("OpenAI APIキー", type="password", placeholder="sk-...")
    st.caption("セッション内のみ使用。保存されません。")
    st.divider()
    st.markdown("**💰 APIコスト目安**")
    st.markdown("gpt-image-1\n- 1コマあたり約 $0.04〜0.08\n- 4コマで約 $0.2〜0.4")
    st.divider()
    st.markdown("**ヒント**")
    st.markdown("元絵を添付するとキャラクターが安定します。")

if not api_key:
    st.info("サイドバーにOpenAI APIキーを入力してください。")
    st.stop()

client = OpenAI(api_key=api_key)

PANEL_W, PANEL_H = 600, 480
BORDER = 6
FONT_SIZE = 22
BUBBLE_PADDING = 12

# 吹き出しスタイル: (rel_x_pct, rel_y_pct, bg_color, outline_color, shape)
# shape: "round" / "oval" / "spiky" / "thought" / "bold"
BUBBLE_PRESETS = [
    (0.54, 0.04, "#FFFFFF", "#222222", "round"),    # 右上・白・通常
    (0.04, 0.04, "#FFFDE7", "#E65100", "spiky"),    # 左上・黄・叫び
    (0.54, 0.60, "#E3F2FD", "#1565C0", "oval"),     # 右下・水色・ふんわり
    (0.04, 0.60, "#FCE4EC", "#AD1457", "thought"),  # 左下・ピンク・思考
    (0.28, 0.04, "#F3E5F5", "#6A1B9A", "bold"),     # 中上・紫・強調
    (0.04, 0.30, "#E8F5E9", "#2E7D32", "round"),    # 左中・緑
    (0.54, 0.30, "#FFF3E0", "#BF360C", "spiky"),    # 右中・オレンジ・叫び
    (0.28, 0.60, "#E1F5FE", "#01579B", "oval"),     # 中下・青
]


def generate_stories(theme: str, character: str, background: str, tone: str) -> list[dict]:
    """GPT-4oで起承転結のある四コマストーリーを3パターン生成"""
    sys_prompt = """あなたは日本の人気四コマ漫画の脚本家です。
以下のルールで【3パターン】のストーリーを考えてください。

【必須ルール】
- 起承転結の構成を厳守：1コマ(起)→2コマ(承)→3コマ(転：予想外の展開)→4コマ(結：誰でもクスッとなるオチ)
- 「転」は読者が予想しないどんでん返しや意外な視点にする
- 「結」のオチはシンプルで日常的な共感を含む笑い。難しいギャグは不可
- セリフは短くインパクト重視（15字以内）
- 3パターンはそれぞれ異なるアプローチでオチを変える

必ず以下のJSON形式のみで返してください：
{
  "stories": [
    {
      "title": "タイトル",
      "approach": "このストーリーのオチのポイント（20字以内）",
      "panels": [
        {
          "number": 1,
          "role": "起",
          "scene": "panel scene description in English for image generation",
          "dialogue": "セリフ（15字以内）",
          "caption": "ナレーション（8字以内、不要なら空文字）"
        },
        {"number":2,"role":"承","scene":"...","dialogue":"...","caption":""},
        {"number":3,"role":"転","scene":"...","dialogue":"...","caption":""},
        {"number":4,"role":"結","scene":"...","dialogue":"...","caption":""}
      ]
    },
    { ...パターン2... },
    { ...パターン3... }
  ]
}"""
    user_msg = f"""テーマ：{theme}
キャラクター：{character}
背景・雰囲気：{background}
トーン：{tone}"""

    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": sys_prompt},
                  {"role": "user", "content": user_msg}],
        response_format={"type": "json_object"}
    )
    data = json.loads(resp.choices[0].message.content)
    return data.get("stories", [])


def generate_panel_image(prompt: str, character: str, background: str = "",
                         ref_image=None) -> Image.Image:
    """1コマの画像を生成"""
    bg_clause = f"background setting: {background}, " if background else ""
    full_prompt = (
        f"single full-color manga panel illustration, one scene only, NOT a comic strip, "
        f"character: {character}, "
        f"scene: {prompt}, "
        f"{bg_clause}"
        f"exaggerated dynamic pose, over-the-top facial expression, dramatic body language, "
        f"very expressive anime-style exaggeration, big reactions, "
        f"vibrant colors, colorful, detailed environment background, "
        f"Japanese manga style, full color illustration, "
        f"no text, no speech bubbles in image, single image only"
    )
    if ref_image is not None:
        buf = io.BytesIO()
        ref_image.convert("RGB").save(buf, format="PNG")
        buf.seek(0)
        resp = client.images.edit(
            model="gpt-image-1",
            image=("reference.png", buf, "image/png"),
            prompt=full_prompt,
            size="1024x1024",
            n=1,
        )
    else:
        resp = client.images.generate(
            model="gpt-image-1",
            prompt=full_prompt,
            size="1024x1024",
            n=1,
        )
    img_bytes = base64.b64decode(resp.data[0].b64_json)
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    return img.resize((PANEL_W, PANEL_H), Image.LANCZOS)


def wrap_text(text: str, max_width: int, font) -> list[str]:
    """フォントに合わせてテキストを折り返す"""
    lines = []
    for line in text.split("\n"):
        if not line:
            lines.append("")
            continue
        current = ""
        for char in line:
            test = current + char
            bbox = font.getbbox(test)
            if bbox[2] - bbox[0] > max_width and current:
                lines.append(current)
                current = char
            else:
                current = test
        if current:
            lines.append(current)
    return lines


def _draw_bubble_shape(draw, x, y, w, h, bg, outline, shape):
    """形状別に吹き出しを描画"""
    import math
    if shape == "spiky":
        cx, cy = x + w // 2, y + h // 2
        rx, ry = w // 2 + 10, h // 2 + 10
        n = 14
        pts = []
        for k in range(n * 2):
            a = math.pi * 2 * k / (n * 2) - math.pi / 2
            ca, sa = math.cos(a), math.sin(a)
            if k % 2 == 0:
                r = math.sqrt(rx**2 + ry**2) + 14
            else:
                r = (rx * ry) / math.sqrt((ry * ca)**2 + (rx * sa)**2) - 4
            pts.append((cx + r * ca, cy + r * sa))
        draw.polygon(pts, fill=bg, outline=outline)
    elif shape == "oval":
        draw.ellipse([x - 6, y, x + w + 6, y + h], fill=bg, outline=outline, width=2)
    elif shape == "thought":
        draw.ellipse([x, y, x + w, y + h], fill=bg, outline=outline, width=2)
        for dx, dy, r in [(w // 2, h + 6, 7), (w // 2 - 6, h + 16, 5), (w // 2 - 10, h + 25, 3)]:
            draw.ellipse([x + dx - r, y + dy - r, x + dx + r, y + dy + r],
                         fill=bg, outline=outline, width=2)
    elif shape == "bold":
        draw.rectangle([x, y, x + w, y + h], fill=bg, outline=outline, width=4)
    else:  # round (default)
        draw.rounded_rectangle([x, y, x + w, y + h], radius=12, fill=bg, outline=outline, width=2)


def add_bubble(draw: ImageDraw.ImageDraw, text: str, y_offset: int,
               font, panel_index: int):
    """吹き出しをパネルに描画。スタイルはコマ番号でローテーション。"""
    if not text:
        return
    rel_x_pct, rel_y_pct, bg_color, outline_color, shape = BUBBLE_PRESETS[panel_index % len(BUBBLE_PRESETS)]
    lines = wrap_text(text, 180, font)
    line_h = font.getbbox("A")[3] + 4
    w = max(font.getbbox(l)[2] for l in lines) + BUBBLE_PADDING * 2
    h = line_h * len(lines) + BUBBLE_PADDING * 2

    rel_x = int(PANEL_W * rel_x_pct)
    rel_y = int(PANEL_H * rel_y_pct)

    x = BORDER + max(4, min(rel_x, PANEL_W - w - 4))
    y = y_offset + max(4, min(rel_y, PANEL_H - h - 4))

    _draw_bubble_shape(draw, x, y, w, h, bg_color, outline_color, shape)
    for i, line in enumerate(lines):
        draw.text((x + BUBBLE_PADDING, y + BUBBLE_PADDING + i * line_h),
                  line, fill="#222222", font=font)


def compose_manga(panels_data: list, panel_images: list[Image.Image]) -> Image.Image:
    """4コマを縦に並べた画像を作成"""
    total_h = PANEL_H * 4 + BORDER * 5
    canvas = Image.new("RGB", (PANEL_W + BORDER * 2, total_h), "white")
    draw = ImageDraw.Draw(canvas)

    font = get_japanese_font(FONT_SIZE)
    font_sm = get_japanese_font(16)

    for i, (pdata, img) in enumerate(zip(panels_data, panel_images)):
        y_offset = BORDER + i * (PANEL_H + BORDER)
        # パネルを貼り付け
        canvas.paste(img, (BORDER, y_offset))
        # 枠線
        draw.rectangle([BORDER, y_offset, BORDER + PANEL_W - 1, y_offset + PANEL_H - 1],
                        outline="black", width=BORDER)

        # セリフ吹き出し
        dialogue = pdata.get("dialogue", "")
        if dialogue:
            add_bubble(draw, dialogue, y_offset, font, i)

        # キャプション（ナレーション）
        caption = pdata.get("caption", "")
        if caption:
            draw.rectangle([BORDER, y_offset, BORDER + len(caption) * 18 + 16, y_offset + 26],
                            fill="black")
            draw.text((BORDER + 8, y_offset + 4), caption, fill="white", font=font_sm)

    return canvas


# ======================================================
# UI
# ======================================================
col1, col2 = st.columns([1, 1])
with col1:
    theme = st.text_input("テーマ・題材", placeholder="例：朝活に行きたくない月曜日")
    character = st.text_area("キャラクター設定", height=100,
        placeholder="例：メガネをかけた60代の男性。ゆるい笑顔でのんびりした性格。")
    background = st.text_input("背景・雰囲気", placeholder="例：朝の自宅・デスク前、暖かい光")
    tone = st.selectbox("トーン", ["ゆるく笑える", "前向き・励まし系", "あるある共感系", "ほっこり日常系"])

with col2:
    ref_upload = st.file_uploader("元絵（任意）", type=["png", "jpg", "jpeg"])
    ref_image = None
    if ref_upload:
        ref_image = Image.open(ref_upload).convert("RGBA")
        st.image(ref_image, caption="参照キャラクター", width=200)
    st.info("元絵を添付するとキャラクターが4コマ通じて安定します。")

if not theme or not character:
    st.warning("テーマとキャラクター設定を入力してください。")
    st.stop()

# セッションステート初期化
if "stories" not in st.session_state:
    st.session_state["stories"] = []
if "selected_story_idx" not in st.session_state:
    st.session_state["selected_story_idx"] = 0

# ── STEP 1: ストーリーを考える ──
if st.button("📝 ストーリーを考える（3パターン）", use_container_width=True):
    with st.spinner("起承転結のストーリーを3パターン考えています…"):
        st.session_state["stories"] = generate_stories(theme, character, background, tone)
        st.session_state["selected_story_idx"] = 0

# ストーリー選択UI
if st.session_state["stories"]:
    st.divider()
    st.subheader("📋 ストーリーを選んでください")

    options = []
    for i, s in enumerate(st.session_state["stories"]):
        options.append(f"パターン{i+1}：{s['title']}　（{s.get('approach','')}）")

    selected = st.radio("", options, index=st.session_state["selected_story_idx"],
                        label_visibility="collapsed")
    st.session_state["selected_story_idx"] = options.index(selected)

    chosen = st.session_state["stories"][st.session_state["selected_story_idx"]]
    panels_data = chosen["panels"]

    cols = st.columns(4)
    roles = {"起": "🟡", "承": "🟢", "転": "🔴", "結": "⭐"}
    for i, p in enumerate(panels_data):
        with cols[i]:
            role = p.get("role", str(i+1))
            emoji = roles.get(role, "")
            st.markdown(f"**{emoji}{role}（{i+1}コマ）**")
            st.markdown(f"「{p.get('dialogue','')}")
            if p.get("caption"):
                st.caption(p["caption"])

    st.divider()

    # ── STEP 2: 画像生成 ──
    if st.button("🚀 この内容で四コマ漫画を生成する", type="primary", use_container_width=True):
        title = chosen.get("title", "四コマ漫画")
        progress = st.progress(0)
        status = st.empty()

        panel_images = []
        preview_cols = st.columns(4)
        for i, pdata in enumerate(panels_data):
            status.text(f"🎨 {i+1}コマ目（{pdata.get('role','')}）を描いています…")
            img = generate_panel_image(pdata["scene"], character, background, ref_image)
            panel_images.append(img)
            with preview_cols[i]:
                st.image(img, caption=f"{i+1}コマ目", use_container_width=True)
            progress.progress(0.2 * (i + 1))

        status.text("🖼️ 四コマに仕上げています…")
        manga = compose_manga(panels_data, panel_images)
        progress.progress(1.0)
        status.text("✅ 完成！")

        st.image(manga, caption=title, use_container_width=False, width=400)

        buf = io.BytesIO()
        manga.save(buf, "PNG")
        st.download_button("📥 PNG をダウンロード", data=buf.getvalue(),
                            file_name="yonkoma.png", mime="image/png",
                            use_container_width=True)

st.divider()
st.caption("Powered by OpenAI gpt-4o + gpt-image-1")
