from pathlib import Path
import re

from app.config import get_settings


settings = get_settings()


def sanitize_path_part(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]", "_", value or "")
    return clean.strip("._") or "sem-identificador"


class XMLStorageService:
    def __init__(self) -> None:
        self.base_path = Path(settings.storage_path)

    def save_xml(
        self,
        empresa_cnpj: str,
        tipo_documento: str,
        ano: int,
        mes: int,
        chave: str,
        xml_content: str,
    ) -> str:
        folder = (
            self.base_path
            / sanitize_path_part(empresa_cnpj)
            / sanitize_path_part(tipo_documento.lower())
            / str(ano)
            / f"{mes:02d}"
        )
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{sanitize_path_part(chave)}.xml"
        file_path.write_text(xml_content, encoding="utf-8")
        return str(file_path)
