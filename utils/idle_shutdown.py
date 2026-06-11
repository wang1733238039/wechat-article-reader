# -*- coding: utf-8 -*-
"""
空闲自动关闭模块
每次请求完成后开始计时，idle_timeout 秒无新请求则自动退出进程
"""

import asyncio
import os
import signal
import threading
from typing import Optional


class IdleShutdown:
    """
    空闲自动关闭器
    """

    def __init__(self, idle_timeout: int = None):
        timeout_env = os.getenv("IDLE_TIMEOUT_SECONDS")
        if timeout_env and int(timeout_env) == 0:
            self.idle_timeout = None  # 禁用自动关闭
        else:
            self.idle_timeout = idle_timeout or (int(timeout_env) if timeout_env else 1200)
        self._timer: Optional[asyncio.TimerHandle] = None
        self._lock = asyncio.Lock()
        self._started = False

    def _schedule_shutdown(self, loop: asyncio.AbstractEventLoop) -> None:
        """调度关闭任务"""

        def _do_shutdown():
            print("\n" + "=" * 60)
            print("[IDLE SHUTDOWN] 空闲超时，进程即将退出")
            print("=" * 60)
            # 给一点时间让日志输出
            threading.Timer(1.0, self._kill_process).start()

        # 取消已有定时器
        if self._timer is not None:
            self._timer.cancel()

        self._timer = loop.call_later(self.idle_timeout, _do_shutdown)
        print(f"[IDLE SHUTDOWN] 已启动，空闲 {self.idle_timeout} 秒后自动退出")

    def _kill_process(self) -> None:
        """真正杀掉进程"""
        pid = os.getpid()
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    async def start(self) -> None:
        """启动空闲检测"""
        if self._started or self.idle_timeout is None:
            return
        self._started = True
        loop = asyncio.get_running_loop()
        self._schedule_shutdown(loop)
        print(f"[IDLE SHUTDOWN] 已启用，无请求 {self.idle_timeout} 秒后自动关闭进程")

    async def on_request(self) -> None:
        """每次有请求时调用，重置计时器"""
        async with self._lock:
            loop = asyncio.get_running_loop()
            self._schedule_shutdown(loop)

    async def stop(self) -> None:
        """停止空闲检测（服务正常关闭时调用）"""
        async with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            print("[IDLE SHUTDOWN] 已停止")


idle_shutdown = IdleShutdown(idle_timeout=1200)
