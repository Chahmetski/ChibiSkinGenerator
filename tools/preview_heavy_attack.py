"""Offline before/after GIFs for the heavy attack; no application 3D viewer."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chibi_skin_generator import animations as current
from chibi_skin_generator.exporter import generate_model
from chibi_skin_generator.geometry import build_chibi_meshes
from chibi_skin_generator.proportions import ProportionSettings
from chibi_skin_generator.rig import build_skeleton
from chibi_skin_generator.uv_tables import uv_table


def main() -> None:
    output = ROOT / "verification_output" / "heavy_attack_review"
    output.mkdir(parents=True, exist_ok=True)
    settings = ProportionSettings()
    meshes = build_chibi_meshes(uv_table(4), 4, settings)
    skeleton = build_skeleton(settings, 4)
    clip = current.build_animation_clips(
        skeleton, animation_names=("AttackHeavySide",), meshes=meshes
    )[0]
    previous_source = subprocess.check_output(
        ["git", "show", "HEAD:src/chibi_skin_generator/animations.py"], cwd=ROOT
    )
    with tempfile.TemporaryDirectory() as temporary:
        module_path = Path(temporary) / "previous.py"
        module_path.write_bytes(previous_source)
        name = "chibi_skin_generator._previous_preview"
        spec = importlib.util.spec_from_file_location(name, module_path)
        previous = importlib.util.module_from_spec(spec)
        sys.modules[name] = previous
        spec.loader.exec_module(previous)
        old_clip = previous.build_animation_clips(
            skeleton, animation_names=("AttackHeavySide",), meshes=meshes
        )[0]

    # Programmatic diagnostic skin: blue tunic, dark trousers, readable face.
    skin = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(skin)
    colors = {"Head": "#e9b88d", "Body": "#3f9bc5", "Arm.L": "#e9b88d",
              "Arm.R": "#e9b88d", "Leg.L": "#354a70", "Leg.R": "#354a70"}
    for name, color in colors.items():
        for rect in uv_table(4)[name].values():
            draw.rectangle((rect.x0, rect.y0, rect.x1-1, rect.y1-1), fill=color)
    draw.rectangle((8, 8, 15, 9), fill="#503b36")
    for x in (10, 13):
        draw.point((x, 12), fill="#202936")
    draw.line((11, 14, 12, 14), fill="#8c4c48")
    skin_path = output / "preview_skin.png"
    skin.save(skin_path)
    result = generate_model(skin_path, "Steve", output, settings,
                            animation_names=("AttackHeavySide",))

    texture = np.asarray(skin)
    direction = np.array((3.0, 1.6, 6.0)); direction /= np.linalg.norm(direction)
    right = np.cross((0, 1, 0), direction); right /= np.linalg.norm(right)
    up = np.cross(direction, right)
    font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 17)

    def render(module, animation, time, title):
        width, height, scale = 360, 400, 142
        rgb = np.full((height, width, 3), (25, 31, 43), dtype=np.uint8)
        depth = np.full((height, width), -np.inf)
        def project(points):
            delta = points - np.array((0, 1.0, 0))
            return np.column_stack((width/2 + delta @ right * scale,
                                    height/2 + 30 - delta @ up * scale, delta @ direction))
        canvas = Image.fromarray(rgb)
        painter = ImageDraw.Draw(canvas)
        for offset in np.arange(-1.5, 1.6, .25):
            for points in ([(offset,0,-1.5),(offset,0,1.5)],
                           [(-1.5,0,offset),(1.5,0,offset)]):
                p = project(np.asarray(points)); painter.line([tuple(v[:2]) for v in p], fill=(43,54,70))
        rgb = np.array(canvas)
        posed = module.posed_mesh_vertices(skeleton, meshes,
                                          module.evaluate_clip(skeleton, animation, time))
        for mesh in meshes:
            if mesh.is_overlay:
                continue
            vertices = posed[mesh.name]; projected = project(vertices)
            for triangle in mesh.faces:
                v = vertices[triangle]; normal = np.cross(v[1]-v[0], v[2]-v[0])
                if normal @ direction <= 0:
                    continue
                p = projected[triangle]
                x0=max(0,int(np.floor(p[:,0].min()))); x1=min(width-1,int(np.ceil(p[:,0].max())))
                y0=max(0,int(np.floor(p[:,1].min()))); y1=min(height-1,int(np.ceil(p[:,1].max())))
                if x1<x0 or y1<y0:
                    continue
                yy,xx=np.mgrid[y0:y1+1,x0:x1+1]; xx=xx+.5; yy=yy+.5
                xa,ya=p[0,:2]; xb,yb=p[1,:2]; xc,yc=p[2,:2]
                denominator=(yb-yc)*(xa-xc)+(xc-xb)*(ya-yc)
                b0=((yb-yc)*(xx-xc)+(xc-xb)*(yy-yc))/denominator
                b1=((yc-ya)*(xx-xc)+(xa-xc)*(yy-yc))/denominator; b2=1-b0-b1
                z=b0*p[0,2]+b1*p[1,2]+b2*p[2,2]
                uv=b0[...,None]*mesh.uv[triangle[0]]+b1[...,None]*mesh.uv[triangle[1]]+b2[...,None]*mesh.uv[triangle[2]]
                tx=np.clip((uv[...,0]*64).astype(int),0,63)
                ty=np.clip(((1-uv[...,1])*64).astype(int),0,63)
                mask=(b0>=0)&(b1>=0)&(b2>=0)&(z>depth[y0:y1+1,x0:x1+1])
                # Mild diagnostic shading makes the silhouette/turn readable.
                normal /= np.linalg.norm(normal)
                shade=.78+.22*max(0,float(normal @ np.array((.3,.7,.6))))
                color=(texture[ty,tx,:3]*shade).astype(np.uint8)
                rgb[y0:y1+1,x0:x1+1][mask]=color[mask]
                depth[y0:y1+1,x0:x1+1][mask]=z[mask]
        canvas=Image.fromarray(rgb); painter=ImageDraw.Draw(canvas)
        painter.text((14,12),title,font=font,fill="#edf3ff")
        painter.text((14,374),f"{time:.2f}s / 0.85s",font=font,fill="#9baec8")
        return canvas

    frames=[]
    for time in np.linspace(0,.85,43):
        frame=Image.new("RGB",(720,400))
        frame.paste(render(previous,old_clip,float(time),"Before"),(0,0))
        frame.paste(render(current,clip,float(time),"Smooth weight shift"),(360,0))
        frames.append(frame)
    frames += [frames[-1]] * 18
    for name,duration in (("comparison.gif",20),("comparison_slow.gif",40)):
        frames[0].save(output/name,save_all=True,append_images=frames[1:],
                       duration=duration,loop=0,optimize=False)
    sheet=Image.new("RGB",(360*4,400))
    for i,time in enumerate((.0,.39,.51,.73)):
        sheet.paste(render(current,clip,time,f"New / {time:.2f}s"),(360*i,0))
    sheet.save(output/"poses.png")
    print(result.output_path)
    print(output/"comparison.gif")


if __name__ == "__main__":
    main()
