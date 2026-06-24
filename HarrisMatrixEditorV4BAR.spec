# -*- mode: python ; coding: utf-8 -*-
a = Analysis(['harris_matrix_editor_v4_bar.py'], pathex=[], binaries=[], datas=[], hiddenimports=['reportlab'], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='HarrisMatrixEditorV4BAR', debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False)
