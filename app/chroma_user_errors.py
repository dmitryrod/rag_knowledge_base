"""Понятные сообщения об ошибках сети/SSL при эмбеддинге Chroma (модель ONNX по HTTPS)."""

from __future__ import annotations


def http_detail_for_chroma_or_embedding_network_error(exc: BaseException) -> str | None:
    """Возвращает текст для HTTP `detail`, если сбой похож на загрузку эмбеддинга / HTTPS.

    Chroma по умолчанию использует ONNX all-MiniLM-L6-v2; при пустом кэше тянет архив с S3.
    """
    text = f"{type(exc).__name__}: {exc}"
    low = text.lower()
    if "handshake" in low and ("timeout" in low or "timed out" in low):
        return (
            "Тайм-аут SSL при эмбеддинге запроса (Chroma, модель all-MiniLM-L6-v2). "
            "Обычно это первая загрузка с https://chroma-onnx-models.s3.amazonaws.com/ — "
            "нужен стабильный HTTPS (интернет, DNS, без блокировки S3; в Docker — DNS/volume для кэша). "
            "Кэш: каталог .cache/chroma под домашним каталогом процесса (в Linux-контейнере часто /root/.cache/chroma). "
            f"Технически: {text}"
        )
    if "read timed out" in low and ("amazonaws" in low or "chroma-onnx" in low or "onnx" in low):
        return (
            "Тайм-аут чтения при загрузке модели эмбеддинга Chroma (HTTPS). "
            "Проверьте сеть и кэш ~/.cache/chroma. "
            f"Технически: {text}"
        )
    return None
