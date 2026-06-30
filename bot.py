"""NoneBot2 主入口"""
import inspect
import logging
import os

import nonebot
from loguru import logger

nonebot.init()

driver = nonebot.get_driver()

_IS_PROD = os.getenv("ENVIRONMENT", "dev").lower() == "prod"

# 生产模式：加载 QQ 官方机器人适配器
if _IS_PROD:
    from nonebot.adapters.qq import Adapter as QQAdapter
    driver.register_adapter(QQAdapter)

# 非 prod 模式下加载 ConsoleAdapter，方便本地调试
if not _IS_PROD:
    try:
        from nonebot.adapters.console import Adapter as ConsoleAdapter
        driver.register_adapter(ConsoleAdapter)  # type: ignore[arg-type]
    except ImportError:
        pass

# prod 环境：将所有日志输出到按天分割的文件
if _IS_PROD:
    _LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(_LOG_DIR, exist_ok=True)

    logger.remove()

    _log_path = os.path.join(_LOG_DIR, "{time:YYYY-MM-DD}.log")
    _sink_cfg = {
        "rotation": "00:00",
        "retention": "7 days",
        "encoding": "utf-8",
        "enqueue": True,
        "backtrace": True,
        "diagnose": False,
        "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} - {message}",
    }
    logger.add(_log_path, **_sink_cfg)

    class _InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno  # type: ignore[assignment]
            frame, depth = inspect.currentframe(), 0
            while frame and frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back  # type: ignore[assignment]
                depth += 1
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    logging.basicConfig(handlers=[_InterceptHandler()], level=logging.DEBUG, force=True)

# 加载插件目录
nonebot.load_plugins("fengsheng-bot2/plugins")

if __name__ == "__main__":
    nonebot.run()

