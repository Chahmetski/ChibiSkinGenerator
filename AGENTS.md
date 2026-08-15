# ChibiSkinGenerator — project constraints

## Scope

- Build a standalone offline Windows desktop application that converts a standard 64x64 Minecraft skin PNG into an editable chibi-style GLB model.
- This repository contains only the first MVP described below. Do not proceed to later stages without an explicit user request.
- The application is not a Blender add-on or Unity project. Do not use the Blender API.

## Required technology

- Python 3.11.9 is explicitly approved for this MVP by the user (overriding the original Python 3.12 requirement).
- PySide6 for the desktop UI.
- Pillow for PNG loading.
- NumPy.
- trimesh and, only if needed, pygltflib for GLB generation.
- pytest for automated tests.
- The application must work fully offline and must not use APIs, MCP, or external online services.
- If Python 3.11.9 or required system tools are unavailable, stop and report what must be installed. Do not substitute another version or stack.

## Input and variants

- Accept only standard Minecraft skin PNG files sized 64x64.
- Support base and overlay texture layers.
- Support Steve arms (4 pixels wide) and Alex arms (3 pixels wide).
- UI must offer Steve, Alex, and Auto selection.

## MVP output

- Export one `.glb` file that Blender can import and edit.
- The source PNG must be embedded in the GLB; no external texture file may be required.
- Export these separate named objects/meshes exactly:
  - `Head`
  - `Head_Overlay`
  - `Body`
  - `Body_Overlay`
  - `Arm.L`
  - `Arm.R`
  - `Arm_Overlay.L`
  - `Arm_Overlay.R`
  - `Leg.L`
  - `Leg.R`
  - `Leg_Overlay.L`
  - `Leg_Overlay.R`

## Model rules

- Use clearly chibi proportions: a large head, small torso, and short legs. Do not recreate standard Minecraft body proportions.
- Every body part must use correct standard Minecraft 64x64 UV coordinates.
- Do not swap or mirror the front, back, left, right, top, or bottom faces.
- Preserve pixel-art rendering without texture smoothing.
- Preserve transparency in overlay pixels.
- Overlay layers must be separate real geometry, slightly expanded relative to the matching base part.
- Base meshes use only the opaque, single-sided `MinecraftSkin_Base` material.
- Overlay meshes use only the alpha-mask, single-sided `MinecraftSkin_Overlay` material with cutoff 0.5; never use alpha blending.
- Export explicit flat outward normals and counter-clockwise front-facing triangle winding.
- Use half-texel-inset UV coordinates and nearest/clamp texture sampling.
- Default to the `Reference Chibi` proportions: a 1-unit head and a 2-unit total base height. Keep the previous dimensions available only as `Legacy`.
- Reference arms must be positioned from body/arm half-widths with a 0.0075 shoulder overlap, pivot at the upper inner shoulder edge, and mirrored 5-degree outward rotations.
- Vertically flip UVs only on the bottom faces of `Head` and `Head_Overlay`; keep every other face unchanged.
- Do not generate geometry per opaque pixel in this MVP.
- Do not add an armature, animation, rounded geometry, volumetric hair, 3D preview, `.blend` export, or executable packaging.

## UI rules

- Provide skin PNG selection, Steve/Alex/Auto selection, output-folder selection, and a Generate button.
- Show clear success and error messages.
- Generation must run outside the GUI thread so the interface remains responsive.

## Project organization and deliverables

- Keep UI, Minecraft skin parser, UV tables, geometry generator, and GLB exporter in separate modules.
- Include `requirements.txt`, `README_RU.md`, `run.bat`, and `setup.bat`.
- Include automated tests for UV tables and exported GLB structure.
- Generate test PNG files programmatically; do not add third-party test assets.
- Do not copy code or assets from Mojavatar Maker.

## Workflow

- Do not build after every change.
- Do not repeat identical checks without a reason.
- Run the necessary test suite once after implementation.
- Do not create Git commits unless the user explicitly requests one.
