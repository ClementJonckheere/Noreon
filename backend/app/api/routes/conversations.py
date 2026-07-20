"""Historique de chat côté serveur (multi-appareils) + dossiers + archivage.

Chaque conversation est propre à (tenant, connexion, utilisateur). Les tours
mémorisent la réponse déjà calculée pour réafficher le fil à l'identique. Une
conversation peut être rangée dans un dossier et archivée (masquée sans être
supprimée).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, get_owned_connection
from app.core.db import get_db
from app.models.connection import Connection
from app.models.conversation import Conversation, ConversationFolder, ConversationTurn
from app.schemas import ConversationCreate, ConversationUpdate, FolderCreate, TurnCreate
from app.services import chat as chat_svc

router = APIRouter(prefix="/connections/{connection_id}/conversations", tags=["conversations"])


def _user_ref(principal: Principal) -> str:
    """Identité stable pour scoper l'historique par utilisateur (repli dev inclus)."""
    if principal.email:
        return principal.email
    if principal.user_id is not None:
        return f"user:{principal.user_id}"
    return "dev-admin"


def _folder_dict(f: ConversationFolder) -> dict:
    return {"id": f.id, "name": f.name, "created_at": f.created_at.isoformat() if f.created_at else None}


def _turn_dict(t: ConversationTurn) -> dict:
    return {
        "id": t.id, "ordinal": t.ordinal, "question": t.question, "deep": t.deep,
        "response": t.response, "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _conv_summary(db: Session, c: Conversation) -> dict:
    count = db.execute(
        select(func.count(ConversationTurn.id)).where(ConversationTurn.conversation_id == c.id)
    ).scalar_one()
    return {
        "id": c.id, "title": c.title, "folder_id": c.folder_id, "archived": c.archived,
        "turn_count": count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _get_conv(db: Session, conn: Connection, principal: Principal, cid: int) -> Conversation:
    conv = db.execute(
        select(Conversation).where(
            Conversation.id == cid,
            Conversation.connection_id == conn.id,
            Conversation.user_ref == _user_ref(principal),
        )
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    return conv


def _get_folder(db: Session, conn: Connection, principal: Principal, fid: int) -> ConversationFolder:
    folder = db.execute(
        select(ConversationFolder).where(
            ConversationFolder.id == fid,
            ConversationFolder.connection_id == conn.id,
            ConversationFolder.user_ref == _user_ref(principal),
        )
    ).scalar_one_or_none()
    if folder is None:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    return folder


# --------------------------------------------------------------------------
# Dossiers
# --------------------------------------------------------------------------
@router.get("/folders")
def list_folders(
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    folders = db.execute(
        select(ConversationFolder).where(
            ConversationFolder.connection_id == conn.id,
            ConversationFolder.user_ref == _user_ref(principal),
        ).order_by(ConversationFolder.name)
    ).scalars().all()
    return [_folder_dict(f) for f in folders]


@router.post("/folders")
def create_folder(
    payload: FolderCreate,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    folder = ConversationFolder(
        tenant_id=conn.tenant_id, connection_id=conn.id,
        user_ref=_user_ref(principal), name=payload.name.strip(),
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _folder_dict(folder)


@router.delete("/folders/{folder_id}")
def delete_folder(
    folder_id: int,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    folder = _get_folder(db, conn, principal, folder_id)
    # Les conversations du dossier deviennent « sans dossier » (SET NULL via FK).
    db.delete(folder)
    db.commit()
    return {"deleted": folder_id}


# --------------------------------------------------------------------------
# Conversations
# --------------------------------------------------------------------------
@router.get("")
def list_conversations(
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
    archived: bool = Query(default=False),
) -> list[dict]:
    convs = db.execute(
        select(Conversation).where(
            Conversation.connection_id == conn.id,
            Conversation.user_ref == _user_ref(principal),
            Conversation.archived.is_(archived),
        ).order_by(Conversation.updated_at.desc())
    ).scalars().all()
    return [_conv_summary(db, c) for c in convs]


@router.post("")
def create_conversation(
    payload: ConversationCreate,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    folder_id = payload.folder_id
    if folder_id is not None:
        _get_folder(db, conn, principal, folder_id)  # valide l'appartenance
    conv = Conversation(
        tenant_id=conn.tenant_id, connection_id=conn.id, user_ref=_user_ref(principal),
        title=(payload.title or "Nouvelle conversation").strip() or "Nouvelle conversation",
        folder_id=folder_id,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {**_conv_summary(db, conv), "turns": []}


@router.get("/{conversation_id}")
def get_conversation(
    conversation_id: int,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    conv = _get_conv(db, conn, principal, conversation_id)
    return {**_conv_summary(db, conv), "turns": [_turn_dict(t) for t in conv.turns]}


@router.patch("/{conversation_id}")
def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    conv = _get_conv(db, conn, principal, conversation_id)
    data = payload.model_dump(exclude_unset=True)
    if "folder_id" in data:
        if data["folder_id"] is not None:
            _get_folder(db, conn, principal, data["folder_id"])
        conv.folder_id = data["folder_id"]
    if "title" in data and data["title"] is not None:
        conv.title = data["title"].strip() or conv.title
    if "archived" in data and data["archived"] is not None:
        conv.archived = data["archived"]
    db.commit()
    db.refresh(conv)
    return _conv_summary(db, conv)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    conv = _get_conv(db, conn, principal, conversation_id)
    db.delete(conv)
    db.commit()
    return {"deleted": conversation_id}


# --------------------------------------------------------------------------
# Tours : exécute la question ET la mémorise dans la conversation
# --------------------------------------------------------------------------
@router.post("/{conversation_id}/turns")
def add_turn(
    conversation_id: int,
    payload: TurnCreate,
    conn: Connection = Depends(get_owned_connection),
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    conv = _get_conv(db, conn, principal, conversation_id)

    response = chat_svc.answer_question(
        db, conn, payload.question,
        user_ref=_user_ref(principal),
        run_analysis=payload.run_analysis, deep_analysis=payload.deep_analysis,
    )
    # Normalisation JSON (dates, Decimal…) avant stockage en colonne JSON.
    resp_dict = jsonable_encoder(response.as_dict())

    ordinal = db.execute(
        select(func.count(ConversationTurn.id)).where(
            ConversationTurn.conversation_id == conv.id
        )
    ).scalar_one()

    turn = ConversationTurn(
        conversation_id=conv.id, ordinal=ordinal,
        question=payload.question, deep=payload.deep_analysis,
        response=resp_dict, error=None,
    )
    db.add(turn)
    # Titre auto à partir de la première question.
    if ordinal == 0 and conv.title in ("", "Nouvelle conversation"):
        title = payload.question.strip().replace("\n", " ")
        conv.title = (title[:42] + "…") if len(title) > 42 else title
    conv.updated_at = func.now()
    db.commit()
    db.refresh(turn)
    return {"turn": _turn_dict(turn), "conversation": _conv_summary(db, conv)}
