"""v0.74.3 — 파일 선택 창이 브라우저 뒤에 열리는 문제 수정.

로컬 서버(백그라운드 프로세스)가 띄운 대화상자는 Windows 포그라운드 잠금 때문에
활성 창(브라우저) 뒤에 열린다. AttachThreadInput + SetForegroundWindow로 앞으로
끌어온다. 실패해도 try/catch로 대화상자는 그대로 뜨고, JS는 '경로 붙여넣기'를 안내.
"""
import base64

from cutdaejang.gui import webui


def test_ps_template_forces_foreground():
    t = webui._PS_PICK_TEMPLATE
    # 포그라운드 잠금을 넘기는 표준 기법이 들어있어야 함
    assert "AttachThreadInput" in t
    assert "SetForegroundWindow" in t
    # P/Invoke 로드 실패해도 대화상자는 떠야 하므로 try/catch로 감쌈
    assert "try {" in t and "} catch {}" in t


def test_ps_template_still_encodes_and_substitutes():
    for k in webui._PICK_KINDS:
        s = webui._PS_PICK_TEMPLATE.replace("@KIND@", k)
        assert "@KIND@" not in s
        # PowerShell -EncodedCommand 형식(UTF-16LE base64)으로 왕복 가능
        enc = base64.b64encode(s.encode("utf-16-le")).decode("ascii")
        assert base64.b64decode(enc).decode("utf-16-le") == s
    # 대화상자 자체는 그대로 있어야 함
    assert "OpenFileDialog" in webui._PS_PICK_TEMPLATE
    assert "FolderBrowserDialog" in webui._PS_PICK_TEMPLATE


def test_pick_timeout_default_reduced():
    # 창이 안 뜨는 상황에서 10분씩 멈추지 않도록 기본 타임아웃을 낮춤
    import inspect

    assert inspect.signature(webui.pick_path).parameters["timeout"].default == 300.0
    assert inspect.signature(webui.pick_video_file).parameters["timeout"].default == 300.0


def test_evaluated_html_js_parses():
    """파이썬이 실제로 만들어내는 _HTML(이스케이프 처리 후)의 JS가 문법상 유효해야 한다.

    v0.74.3 회귀 방지: JS 문자열에 '\\n'(홑따옴표+n)을 쓰면 non-raw 파이썬 문자열이
    실제 줄바꿈으로 바꿔 문자열 리터럴이 깨지고 페이지 전체 JS가 죽었다. 반드시
    소스가 아니라 '평가된' _HTML 을 검사해야 이 부류를 잡는다. node 없으면 skip.
    """
    import os
    import re
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if not node:
        import pytest

        pytest.skip("node 미설치 — JS 파싱 검사 생략")
    html = webui._HTML
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert scripts, "no <script> block found"
    js = "\n;\n".join(scripts)
    path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(js)
            path = f.name
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-800:]
    finally:
        if path:
            os.unlink(path)
