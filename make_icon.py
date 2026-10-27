from PIL import Image, ImageDraw
import os

SIZE = 512
im = Image.new("RGBA", (SIZE, SIZE), (9, 11, 20, 255))
px = im.load()
for y in range(SIZE):
    for x in range(SIZE):
        glow = max(0.0, 1.0 - (((x-250)**2 + (y-250)**2) ** 0.5) / 430)
        px[x, y] = (int(9+18*glow), int(11+7*glow), int(24+30*glow), 255)

d = ImageDraw.Draw(im)
# Rounded square neon border
d.rounded_rectangle((20,20,492,492), radius=104, outline=(91,73,255,255), width=9)
# feather silhouette angled from lower-left to upper-right
# Broad vane on right side
d.polygon([(92,397),(151,300),(202,209),(273,126),(366,67),(357,151),(330,190),(359,185),(330,230),(298,253),(324,251),(289,291),(251,310),(273,313),(232,349),(185,365),(147,400)], fill=(108,69,255,255))
# left vane with cyan-blue gradient-like facets
d.polygon([(92,397),(151,300),(202,209),(273,126),(253,205),(221,249),(205,291),(171,326),(145,363)], fill=(36,165,255,255))
d.polygon([(151,300),(202,209),(253,151),(235,216),(203,257)], fill=(66,119,255,255))
d.polygon([(171,326),(205,291),(253,248),(232,289),(194,329)], fill=(48,114,255,255))
d.polygon([(194,329),(232,289),(281,270),(251,310),(218,339)], fill=(75,92,255,255))
d.polygon([(218,339),(251,310),(298,291),(273,327),(232,349)], fill=(114,73,255,255))
d.polygon([(232,349),(273,327),(306,311),(276,346),(240,363)], fill=(150,65,255,255))
# central rachis, tapered diagonal shaft
d.line([(87,416),(146,344),(204,266),(260,187),(319,109),(365,65)], fill=(54,208,255,255), width=12)
d.line([(91,412),(149,342),(206,264),(262,186),(320,108),(364,66)], fill=(190,236,255,255), width=3)
# small highlight
d.arc((50,50,462,462), 200, 285, fill=(39,126,255,170), width=3)
os.makedirs("assets", exist_ok=True)
im.convert("RGB").save("assets/az-tool-icon.png", optimize=True)
im.save("assets/az-tool-icon.ico", format="ICO", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
