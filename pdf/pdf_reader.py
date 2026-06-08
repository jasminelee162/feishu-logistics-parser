""" 
PDF 文本读取器（基于 PyMuPDF / fitz）。

提供类 `PDFReader`，用于安全、可追踪地从 PDF 中提取文本。
该模块遵循企业级规范：包含明确类型注解、完整中文注释、日志输出、以及针对常见错误的异常处理。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
import logging

try:
    import fitz  # PyMuPDF
except Exception as exc:  # pragma: no cover - 环境依赖
    fitz = None
    _FITZ_IMPORT_ERROR = exc
else:
    _FITZ_IMPORT_ERROR = None

logger = logging.getLogger("PDFReader")
if not logger.handlers:
    # 如果上层未配置 logging，设置一个简单的 handler，避免无日志输出
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class PDFReader:
    """基于 PyMuPDF 的 PDF 文本读取器。

    功能：
        - 打开 PDF 文件
        - 遍历所有页面并提取文本
        - 将每页文本拼接为一个字符串并返回

    日志（info 级别）：
        [PDFReader] 开始读取文件
        [PDFReader] 第X页提取完成
        [PDFReader] PDF读取完成

    异常：
        FileNotFoundError: 当文件不存在时抛出
        RuntimeError: 当 PyMuPDF 未安装、PDF 无法打开/损坏、或读取失败时抛出
    """

    def __init__(self, logger_instance: Optional[logging.Logger] = None) -> None:
        """初始化 PDFReader。

        参数:
            logger_instance: 可选的 logging.Logger 实例；若未提供使用模块内默认 logger。
        """
        self._logger = logger_instance or logger

    def read_pdf(self, file_path: str) -> str:
        """读取并返回指定 PDF 的全部文本。

        参数:
            file_path: PDF 文件路径（本地文件）

        返回:
            包含所有页面文本的字符串（按页以换行分隔）

        抛出:
            FileNotFoundError: 文件不存在
            RuntimeError: PyMuPDF 未安装或 PDF 打开/解析失败
        """
        self._logger.info("[PDFReader] 开始读取文件 %s", file_path)

        p = Path(file_path)
        if not p.exists():
            msg = f"PDF 文件未找到: {file_path}"
            self._logger.error("[PDFReader] %s", msg)
            raise FileNotFoundError(msg)

        if _FITZ_IMPORT_ERROR is not None or fitz is None:
            msg = (
                "PyMuPDF (fitz) 未安装或导入失败，请运行 `pip install PyMuPDF` 后重试。"
            )
            self._logger.error("[PDFReader] %s", msg)
            raise RuntimeError(msg)

        try:
            doc = fitz.open(str(p))
        except Exception as exc:
            msg = f"无法打开 PDF（可能已损坏）: {file_path}"
            self._logger.exception("[PDFReader] %s", msg)
            raise RuntimeError(msg) from exc

        texts = []
        try:
            for page_index in range(len(doc)):
                try:
                    page = doc.load_page(page_index)
                    page_text = page.get_text()
                    texts.append(page_text or "")
                    # 页号以 1 开始更符合人类习惯
                    self._logger.info("[PDFReader] 第%d页提取完成", page_index + 1)
                except Exception as page_exc:
                    # 记录单页提取失败，但继续尝试其余页面
                    self._logger.exception(
                        "[PDFReader] 第%d页提取失败，继续处理剩余页。", page_index + 1
                    )
                    texts.append("")
        except Exception as exc:
            msg = f"读取 PDF 文本过程中发生错误: {file_path}"
            self._logger.exception("[PDFReader] %s", msg)
            raise RuntimeError(msg) from exc
        finally:
            try:
                doc.close()
            except Exception:
                # 忽略关闭时的错误，但记录日志
                self._logger.debug("[PDFReader] 关闭文档时发生异常（已忽略）")

        self._logger.info("[PDFReader] PDF读取完成 %s", file_path)
        return "\n".join(texts)


def read_pdf_text(path: str) -> str:
    """兼容函数：直接使用 `PDFReader` 读取并返回文本字符串。

    该函数便于快速迁移旧代码调用方式。
    """
    reader = PDFReader()
    return reader.read_pdf(path)
