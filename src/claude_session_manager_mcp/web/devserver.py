#!/usr/bin/env python3
"""개발 서버 - 파일 변경 감지 자동 재시작"""
import os
import subprocess
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

WATCH_EXTENSIONS = {'.py', '.html', '.css', '.js'}
WATCH_DIRS = ['templates', '.']
IGNORE_PATTERNS = {'__pycache__', '.git', 'venv', '.bak'}


class ReloadHandler(FileSystemEventHandler):
    def __init__(self, process_starter):
        self.process_starter = process_starter
        self.last_reload = 0
        self.debounce_seconds = 1  # 1초 내 중복 이벤트 무시

    def on_modified(self, event):
        if event.is_directory:
            return
        self._handle_change(event.src_path)

    def on_created(self, event):
        if event.is_directory:
            return
        self._handle_change(event.src_path)

    def _handle_change(self, path):
        # 무시할 패턴 체크
        for pattern in IGNORE_PATTERNS:
            if pattern in path:
                return

        # 확장자 체크
        ext = Path(path).suffix
        if ext not in WATCH_EXTENSIONS:
            return

        # 디바운싱
        now = time.time()
        if now - self.last_reload < self.debounce_seconds:
            return
        self.last_reload = now

        print(f"\n🔄 File changed: {Path(path).name}")
        self.process_starter()


class DevServer:
    def __init__(self):
        self.process = None
        self.base_dir = Path(__file__).parent

    def start_app(self):
        """Flask 앱 시작"""
        if self.process:
            self.process.terminate()
            self.process.wait()

        env = os.environ.copy()
        env['FLASK_ENV'] = 'development'

        self.process = subprocess.Popen(
            [sys.executable, 'app.py'],
            cwd=self.base_dir,
            env=env
        )
        print("✅ Server started")

    def run(self):
        """개발 서버 실행"""
        print("🚀 Starting dev server with file watching...")
        print(f"📁 Watching: {', '.join(WATCH_EXTENSIONS)}")
        print("Press Ctrl+C to stop\n")

        # 초기 앱 시작
        self.start_app()

        # 파일 감시 설정
        event_handler = ReloadHandler(self.start_app)
        observer = Observer()

        for watch_dir in WATCH_DIRS:
            watch_path = self.base_dir / watch_dir
            if watch_path.exists():
                observer.schedule(event_handler, str(watch_path), recursive=True)

        observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping dev server...")
            observer.stop()
            if self.process:
                self.process.terminate()

        observer.join()


if __name__ == '__main__':
    DevServer().run()
