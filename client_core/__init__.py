"""client_core: 모니터링 클라이언트 모듈화 패키지.

기존 agent.py의 단일 파일 구조를 책임 단위로 분리.
- config: 설정 로딩/기본값
- identity: PC 고유 식별
- timeslot: 시간대 슬롯 판정
- collector: psutil/GPU 등 메트릭 수집
- window: 슬라이딩 윈도우
- detector: Layer1 규칙 기반 탐지
- sender: ML 서버 전송 + 로컬 큐
- model: 페이로드/알람 dataclass
- runtime: 메인 루프 오케스트레이션
"""

# Windows 에서 GPUtil 이 호출하는 nvidia-smi.exe 같은 subprocess 가
# 콘솔 창을 깜빡이게 만든다. PyInstaller --noconsole 은 메인 프로세스만
# 콘솔을 숨기므로, 자식 프로세스에도 CREATE_NO_WINDOW 를 강제한다.
# (학생 PC 백그라운드 운영 시 깜빡임 방지)
import sys as _sys
if _sys.platform == "win32":
    import subprocess as _subprocess
    _CREATE_NO_WINDOW = 0x08000000
    _orig_popen_init = _subprocess.Popen.__init__

    def _no_window_popen_init(self, *args, **kwargs):
        kwargs.setdefault("creationflags", 0)
        kwargs["creationflags"] |= _CREATE_NO_WINDOW
        _orig_popen_init(self, *args, **kwargs)

    _subprocess.Popen.__init__ = _no_window_popen_init


__version__ = "9.0.0"
