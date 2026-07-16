from PIL import Image, ImageDraw

NAVY_DARK = (22, 49, 79)
BLUE_MID = (58, 111, 150)
BLUE_LIGHT = (111, 160, 196)


def make_base(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Diagonal gradient background, rounded square (mirrors .brand-mark CSS gradient)
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            if t < 0.6:
                tt = t / 0.6
                r = int(NAVY_DARK[0] + (BLUE_MID[0] - NAVY_DARK[0]) * tt)
                g = int(NAVY_DARK[1] + (BLUE_MID[1] - NAVY_DARK[1]) * tt)
                b = int(NAVY_DARK[2] + (BLUE_MID[2] - NAVY_DARK[2]) * tt)
            else:
                tt = (t - 0.6) / 0.4
                r = int(BLUE_MID[0] + (BLUE_LIGHT[0] - BLUE_MID[0]) * tt)
                g = int(BLUE_MID[1] + (BLUE_LIGHT[1] - BLUE_MID[1]) * tt)
                b = int(BLUE_MID[2] + (BLUE_LIGHT[2] - BLUE_MID[2]) * tt)
            img.putpixel((x, y), (r, g, b, 255))

    mask = Image.new("L", (size, size), 0)
    mdraw = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    mdraw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.putalpha(mask)

    # Envelope + checkmark glyph (same shape as ui/index.html brand-mark svg), scaled to icon
    draw = ImageDraw.Draw(img)
    s = size / 24.0
    w = max(1, round(1.7 * s))
    w_check = max(1, round(1.6 * s))
    w_badge_ring = max(1, round(1.3 * s))

    def pt(x, y):
        return (x * s, y * s)

    # Envelope body (rounded rect outline)
    draw.rounded_rectangle(
        [pt(1.5, 5), pt(16.5, 16)],
        radius=2.2 * s,
        outline=(255, 255, 255, 255),
        width=w,
    )
    # Envelope flap
    draw.line([pt(2.2, 6.3), pt(9, 11.6), pt(15.8, 6.3)], fill=(255, 255, 255, 255), width=w, joint="curve")

    # Checkmark badge circle
    badge_r = 5.3 * s
    badge_cx, badge_cy = pt(18.4, 16.9)
    draw.ellipse(
        [badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r],
        fill=NAVY_DARK + (255,),
        outline=(255, 255, 255, 255),
        width=w_badge_ring,
    )
    draw.line(
        [pt(16.2, 17), pt(17.9, 18.7), pt(20.9, 15.3)],
        fill=(255, 255, 255, 255),
        width=w_check,
        joint="curve",
    )
    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
images = [make_base(s) for s in sizes]
images[-1].save(
    "ui/app_icon.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes],
)
print("Icon saved.")
