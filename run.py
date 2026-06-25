import subprocess
import sys
import time

def main():
    print("🚀 FastAPI 백엔드와 Streamlit 프론트엔드를 동시에 시작합니다...\n")
    
    # 1. FastAPI 백엔드 실행
    api_process = subprocess.Popen([sys.executable, "run_api.py"])
    
    # 서버가 뜨는 데 필요한 약간의 대기 시간 (선택 사항)
    time.sleep(7)
    
    # 2. Streamlit 프론트엔드 실행
    # sys.executable을 사용하면 현재 활성화된 가상환경(ml_env)의 파이썬을 확실하게 사용합니다.
    web_process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "web/streamlit_app.py", "--server.port", "8501"])
    
    try:
        # 두 프로세스가 종료될 때까지 대기
        api_process.wait()
        web_process.wait()
    except KeyboardInterrupt:
        print("\n🛑 종료 신호(Ctrl+C)를 받았습니다. 두 서버를 종료합니다...")
        api_process.terminate()
        web_process.terminate()
        api_process.wait()
        web_process.wait()
        print("✅ 안전하게 종료되었습니다.")

if __name__ == "__main__":
    main()