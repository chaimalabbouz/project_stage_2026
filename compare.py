import cv2, glob, os
import numpy as np
from skimage.metrics import structural_similarity as ssim
import lpips, torch

FIGMA_DIR = "/mnt/c/Users/binitns/Desktop/figma"
SITE_DIR  = "/mnt/c/Users/binitns/Desktop/generate"

loss_fn = lpips.LPIPS(net='alex', verbose=False)

def to_tensor(img):
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = torch.from_numpy(img).permute(2, 0, 1).float() / 127.5 - 1
    return img.unsqueeze(0)

def find(folder, name):
    hits = glob.glob(os.path.join(folder, name + ".*"))
    return hits[0] if hits else None

# Liste des noms (sans extension) presents dans le dossier figma
noms = sorted({os.path.splitext(os.path.basename(p))[0]
               for p in glob.glob(os.path.join(FIGMA_DIR, "*"))})

resultats = []
print(f"{'Page':<8}{'SSIM':>8}{'LPIPS':>9}")
print("-" * 25)

for nom in noms:
    pf, ps = find(FIGMA_DIR, nom), find(SITE_DIR, nom)
    if not pf or not ps:
        print(f"{nom:<8}  paire incomplete, ignoree")
        continue

    figma, site = cv2.imread(pf), cv2.imread(ps)
    if figma is None or site is None:
        print(f"{nom:<8}  image illisible, ignoree")
        continue

    site = cv2.resize(site, (figma.shape[1], figma.shape[0]))

    s = ssim(cv2.cvtColor(figma, cv2.COLOR_BGR2GRAY),
             cv2.cvtColor(site,  cv2.COLOR_BGR2GRAY))
    l = loss_fn(to_tensor(figma), to_tensor(site)).item()

    resultats.append((s, l))
    print(f"{nom:<8}{s:>8.3f}{l:>9.3f}")

if resultats:
    a = np.array(resultats)
    print("-" * 25)
    print(f"{'MOYENNE':<8}{a[:,0].mean():>8.3f}{a[:,1].mean():>9.3f}")
    print(f"{'ECART':<8}{a[:,0].std():>8.3f}{a[:,1].std():>9.3f}")
    print(f"\n{len(resultats)} paires comparees")