"""README screenshots, taken from the demo build and the real digest renderers.

    uv run scripts/build_demo.py
    uv run --with playwright --with pillow scripts/screenshots.py
    (once: uv run --with playwright playwright install chromium)

Writes docs/assets/*.png. PLAYWRIGHT_CHROMIUM=<path> picks a specific browser binary.
"""
import io, json, os, re, sys, pathlib
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stackscout import render  # noqa: E402

DEMO = (ROOT / "docs" / "index.html")
OUT = ROOT / "docs" / "assets"; OUT.mkdir(parents=True, exist_ok=True)
CHROME = os.environ.get("PLAYWRIGHT_CHROMIUM") or None

def save(png: bytes, name: str, width: int | None = None):
    img = Image.open(io.BytesIO(png)).convert("RGB")
    if width and img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(OUT / name, optimize=True)
    print(f"{name}: {img.width}x{img.height} {(OUT / name).stat().st_size // 1024} KB")

snap = json.loads(re.search(r"window.SS_DEMO = (\{.*?\});</script>", DEMO.read_text(), re.S).group(1).replace("<\\/", "</"))

with sync_playwright() as p:
    b = p.chromium.launch(executable_path=CHROME)
    ctx = b.new_context(viewport={"width": 1280, "height": 820}, locale="en-US", device_scale_factor=1)
    page = ctx.new_page()
    page.goto(DEMO.as_uri()); page.evaluate("localStorage.setItem('ss-theme','light')"); page.reload(); page.wait_for_selector(".ovcard")
    page.evaluate("document.querySelector('.demobar')?.remove()")
    def clean():
        page.evaluate("document.querySelector('.demobar')?.remove(); document.querySelectorAll('.toast').forEach(e => e.remove())")

    save(page.screenshot(), "overview.png")
    # New models & AI: the feed, then the rivals drawer
    page.locator("aside .filters button").nth(1).click(); page.wait_for_timeout(250); clean()
    page.locator(".titlebtn").first.click(); page.wait_for_selector(".drawer .rival"); page.wait_for_timeout(250); clean()
    save(page.screenshot(), "rivals.png")
    page.keyboard.press("Escape")
    # Vs. my stack: grouped list, then one comparison's details and its sources
    page.locator("nav.topnav .tab").nth(1).click(); page.wait_for_timeout(300); clean()
    save(page.screenshot(), "vs-stack.png")
    # The comparison with full texts (nothing cut with "…") and the most independent sources.
    shown = page.locator("article.item strong").all_inner_texts()
    best = max((c for k, c in snap["comparisons"].items()
                if not c.get("fit", "").endswith("…") and not c.get("what_is_new", "").endswith("…")
                and any(c["new"] == n or n.startswith(c["new"] + " ") for n in shown)),
               key=lambda c: (c.get("independent_sources", 0), len(c.get("pros", [])) + len(c.get("cons", []))))
    print("detail:", best["new"], "vs", best["current"])
    art = page.locator("article.item").filter(has=page.locator("strong", has_text=best["new"])).first
    art.locator("button.cmpline").click(); page.wait_for_selector(".drawer .verdict"); page.wait_for_timeout(250); clean()
    save(page.locator(".drawer").screenshot(), "stack-detail.png", width=560)
    page.locator(".drawer").evaluate("d => d.scrollTop = d.scrollHeight"); page.wait_for_timeout(200)
    save(page.locator(".drawer").screenshot(), "sources-cited.png", width=560)
    page.keyboard.press("Escape")
    # Profile and sources
    page.locator("nav.topnav .tab").nth(3).click(); page.wait_for_timeout(300); clean()
    save(page.screenshot(), "profile.png")
    page.locator("nav.topnav .tab").nth(2).click(); page.wait_for_timeout(400); clean()
    save(page.screenshot(), "sources.png")
    # Dark theme in Japanese, light in Vietnamese
    page.locator("nav.topnav .tab").first.click(); page.locator("aside .filters button").first.click()
    page.locator("nav.topnav select").select_option("ja"); page.locator("header .iconbtn").click(); page.wait_for_timeout(300); clean()
    save(page.screenshot(), "dark-ja.png", width=900)
    page.locator("header .iconbtn").click(); page.locator("nav.topnav select").select_option("vi"); page.wait_for_timeout(300); clean()
    save(page.screenshot(), "light-vi.png", width=900)
    ctx.close()

    # Phone: the compare tab
    m = b.new_context(viewport={"width": 390, "height": 780}, locale="en-US", device_scale_factor=2, is_mobile=True).new_page()
    m.goto(DEMO.as_uri()); m.wait_for_selector(".ovcard"); m.evaluate("document.querySelector('.demobar')?.remove()")
    m.locator("aside .filters button").nth(1).click(); m.wait_for_timeout(200)
    m.locator(".titlebtn").first.click(); m.wait_for_selector(".drawer .rival"); m.wait_for_timeout(300)
    save(m.screenshot(), "mobile.png", width=390)
    m.context.close()

    # The weekly digest as it is delivered: email (HTML) and Telegram (HTML message)
    model = render.build(snap["report"], snap["comparisons"], snap["market"], "en")
    _, _, page_html = render.email(model)
    e = b.new_context(viewport={"width": 760, "height": 900}).new_page()
    e.set_content('<div style="background:#f3f4f6;padding:24px"><div style="background:#fff;border-radius:12px;padding:24px 28px;'
                  'box-shadow:0 1px 3px rgba(0,0,0,.08)"><div style="font:600 13px -apple-system,Segoe UI,sans-serif;color:#6b7280;'
                  f'margin-bottom:14px">Subject: {model["subject"]}</div>{page_html}</div></div>')
    save(e.screenshot(), "digest-email.png")
    msg = render.telegram(model)[0]
    e.set_content('<div style="background:#0e1621;padding:24px;min-height:900px"><div style="max-width:620px;background:#182533;color:#e9edef;'
                  'border-radius:14px;padding:14px 16px;font:14px/1.5 -apple-system,Segoe UI,sans-serif;white-space:pre-wrap">'
                  + msg.replace("<a ", '<a style="color:#6ab3f3" ') + '</div></div>')
    save(e.screenshot(), "digest-telegram.png")
    b.close()


# ---- composites: one landscape image per README row (text left, image right)
def compose(names: list[str], out: str, height: int = 820, gap: int = 24, pad: int = 24):
    imgs = [Image.open(OUT / n).convert("RGB") for n in names]
    imgs = [i.resize((round(i.width * height / i.height), height), Image.LANCZOS) for i in imgs]
    canvas = Image.new("RGB", (sum(i.width for i in imgs) + gap * (len(imgs) - 1) + 2 * pad, height + 2 * pad), (243, 244, 246))
    x = pad
    for i in imgs:
        canvas.paste(i, (x, pad)); x += i.width + gap
    buf = io.BytesIO(); canvas.save(buf, "PNG"); save(buf.getvalue(), out, width=1400)


compose(["stack-detail.png", "sources-cited.png"], "claims.png")
compose(["digest-email.png", "digest-telegram.png"], "digests.png", height=900)
# Two desktop shots stacked, the phone beside them: close to square, readable at half width.
def compose_looks():
    dark, light, phone = (Image.open(OUT / n).convert("RGB") for n in ("dark-ja.png", "light-vi.png", "mobile.png"))
    gap, pad = 24, 24
    col_h = dark.height + gap + light.height
    phone = phone.resize((round(phone.width * col_h / phone.height), col_h), Image.LANCZOS)
    canvas = Image.new("RGB", (dark.width + gap + phone.width + 2 * pad, col_h + 2 * pad), (243, 244, 246))
    canvas.paste(dark, (pad, pad)); canvas.paste(light, (pad, pad + dark.height + gap))
    canvas.paste(phone, (pad + dark.width + gap, pad))
    buf = io.BytesIO(); canvas.save(buf, "PNG"); save(buf.getvalue(), "looks.png", width=1400)


compose_looks()
