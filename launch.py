"""Windows bundle entry point."""
if __name__ == "__main__":
    import json
    import os
    from pathlib import Path
    import sys
    import traceback
    try:
        from chibi_skin_generator.app import main
        raise SystemExit(main())
    except Exception:
        error = traceback.format_exc()
        if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
            folder = Path(sys.argv[2])
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "report.json").write_text(json.dumps({"ok": False, "error": error}), encoding="utf-8")
        else:
            folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ChibiSkinGenerator"
            folder.mkdir(parents=True, exist_ok=True)
            log = folder / "error.log"
            log.write_text(error, encoding="utf-8")
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, f"Ошибка запуска. Подробности: {log}", "ChibiSkinGenerator", 16)
        raise SystemExit(1)
