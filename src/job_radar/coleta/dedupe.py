"""Upsert de vagas: uma `vaga` global por hash, um `vaga_fonte` por aparição (RN05-RN06)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from job_radar.models import Vaga, VagaFonte
from job_radar.schemas.vaga import VagaNormalizada


def registrar_vaga(sessao: Session, normalizada: VagaNormalizada) -> tuple[Vaga, bool]:
    """Retorna (vaga, nova). `nova` é False se a vaga já existia por qualquer fonte."""
    aparicao = sessao.get(VagaFonte, (normalizada.fonte_id, normalizada.id_externo))
    if aparicao is not None:
        aparicao.visto_em = func.now()
        vaga = sessao.get_one(Vaga, aparicao.vaga_id)
        return vaga, False

    vaga = sessao.scalar(select(Vaga).where(Vaga.hash_dedupe == normalizada.hash_dedupe))
    nova = vaga is None
    if vaga is None:
        vaga = Vaga(
            hash_dedupe=normalizada.hash_dedupe,
            titulo=normalizada.titulo,
            empresa=normalizada.empresa,
            descricao=normalizada.descricao,
            cidade=normalizada.cidade,
            uf=normalizada.uf,
            modalidade=normalizada.modalidade,
            nivel=normalizada.nivel,
            url_canonica=normalizada.url_canonica,
            publicada_em=normalizada.publicada_em,
        )
        sessao.add(vaga)
        sessao.flush()

    sessao.add(
        VagaFonte(
            vaga_id=vaga.id,
            fonte_id=normalizada.fonte_id,
            id_externo=normalizada.id_externo,
            url=normalizada.url,
            dados_brutos=normalizada.dados_brutos,
        )
    )
    sessao.flush()
    return vaga, nova
