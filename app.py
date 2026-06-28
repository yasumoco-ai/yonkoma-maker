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


def generate_story(theme: str, character: str, background: str, tone: str) -> dict:
    """GPT-4oで四コマのストーリーを生成"""
    sys_prompt = """あなたは四コマ漫画の脚本家です。
指定されたテーマ・キャラクター・背景・トーンで、オチのある四コマ漫画のストーリーを考えてください。
必ず以下のJSON形式で返してください（他の文章は不要）：
{
  "title": "タイトル",
  "panels": [
    {
      "number": 1,
      "scene": "シーンの説明（英語で画像生成プロンプトとして使う）",
      "dialogue": "セリフ（日本語、20字以内）",
      "caption": "ナレーション（任意、10字以内。不要なら空文字）"
    },
    ...4コマ分...
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
    return json.loads(resp.choices[0].message.content)


def generate_panel_image(prompt: str, character: str, ref_image=None) -> Image.Image:
    """1コマの画像を生成"""
    full_prompt = (
        f"single manga panel illustration, one scene only, NOT a comic strip, "
        f"character: {character}, "
        f"scene: {prompt}, "
        f"clean line art, white background, expressive, Japanese manga style, "
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


def add_bubble(draw: ImageDraw.ImageDraw, text: str, rel_x: int, rel_y: int,
               font, y_offset: int):
    """吹き出しを描画。rel_x/rel_y はパネル左上からの相対座標。"""
    if not text:
        return
    lines = wrap_text(text, 180, font)
    line_h = font.getbbox("A")[3] + 4
    w = max(font.getbbox(l)[2] for l in lines) + BUBBLE_PADDING * 2
    h = line_h * len(lines) + BUBBLE_PADDING * 2

    # パネル内に収める（絶対座標に変換）
    x = BORDER + max(4, min(rel_x, PANEL_W - w - 4))
    y = y_offset + max(4, min(rel_y, PANEL_H - h - 4))

    draw.rounded_rectangle([x, y, x + w, y + h], radius=10,
                            fill="white", outline="black", width=2)
    for i, line in enumerate(lines):
        draw.text((x + BUBBLE_PADDING, y + BUBBLE_PADDING + i * line_h),
                  line, fill="black", font=font)


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

        # セリフ吹き出し（rel_x/rel_y はパネル内の相対座標）
        dialogue = pdata.get("dialogue", "")
        if dialogue:
            add_bubble(draw, dialogue, PANEL_W - 200, 10, font, y_offset)

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

if st.button("🚀 四コマ漫画を生成する", type="primary", use_container_width=True):
    progress = st.progress(0)
    status = st.empty()

    # Step 1: ストーリー生成
    status.text("📝 ストーリーを考えています…")
    story = generate_story(theme, character, background, tone)
    progress.progress(0.1)

    title = story.get("title", "四コマ漫画")
    panels_data = story.get("panels", [])

    with st.expander(f"📋 生成されたストーリー「{title}」", expanded=True):
        for p in panels_data:
            st.markdown(f"**{p['number']}コマ目**：{p.get('dialogue','（セリフなし）')} / {p.get('scene','')[:60]}")

    # Step 2: 各コマの画像生成
    panel_images = []
    preview_cols = st.columns(4)
    for i, pdata in enumerate(panels_data):
        status.text(f"🎨 {i+1}コマ目を描いています…")
        img = generate_panel_image(pdata["scene"], character, ref_image)
        panel_images.append(img)
        with preview_cols[i]:
            st.image(img, caption=f"{i+1}コマ目", use_container_width=True)
        progress.progress(0.1 + 0.2 * (i + 1))

    # Step 3: 合成
    status.text("🖼️ 四コマに仕上げています…")
    manga = compose_manga(panels_data, panel_images)
    progress.progress(1.0)
    status.text("✅ 完成！")

    # 表示 & ダウンロード
    st.image(manga, caption=title, use_container_width=False, width=400)

    buf = io.BytesIO()
    manga.save(buf, "PNG")
    st.download_button("📥 PNG をダウンロード", data=buf.getvalue(),
                        file_name="yonkoma.png", mime="image/png",
                        use_container_width=True)

st.divider()
st.caption("Powered by OpenAI gpt-4o + gpt-image-1")
