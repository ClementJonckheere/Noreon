"""Historique de chat rattaché à un ESPACE (multi-appareils) + dossiers.

Miroir des conversations par connexion, mais scopé (espace, utilisateur). Un
tour choisit sa source (BDD rattachée à l'espace) et applique la gouvernance de
l'espace.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal
from app.api.routes.spaces import get_space
from app.core.db import get_db
from app.models.connection import Connection
from app.models.conversation import Conversation, ConversationFolder, ConversationTurn
from app.models.space import Space
from app.schemas import ConversationCreate, ConversationUpdate, FolderCreate, SpaceTurnCreate
from app.services import chat as chat_svc
from app.services import spaces as spaces_svc

router = APIRouter(prefix="/spaces/{space_id}/conversations", tags=["space-conversations"])


def _user_ref(p: Principal) -> str:
    if p.email:
        return p.email
    if p.user_id is not None:
        return f"user:{p.user_id}"
    return "dev-admin"


def _folder_dict(f: ConversationFolder) -> dict:
    return {"id": f.id, "name": f.name, "created_at": f.created_at.isoformat() if f.created_at else None}


def _turn_dict(t: ConversationTurn) -> dict:
    return {
        "id": t.id, "ordinal": t.ordinal, "question": t.question, "deep": t.deep,
        "connection_id": t.connection_id, "response": t.response, "error": t.error,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _summary(db: Session, c: Conversation) -> dict:
    count = db.execute(
        select(func.count(ConversationTurn.id)).where(ConversationTurn.conversation_id == c.id)
    ).scalar_one()
    return {
        "id": c.id, "title": c.title, "folder_id": c.folder_id, "archived": c.archived,
        "turn_count": count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _get_conv(db: Session, space: Space, p: Principal, cid: int) -> Conversation:
    conv = db.execute(
        select(Conversation).where(
            Conversation.id == cid,
            Conversation.space_id == space.id,
            Conversation.user_ref == _user_ref(p),
        )
    ).scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation introuvable.")
    return conv


def _get_folder(db: Session, space: Space, p: Principal, fid: int) -> ConversationFolder:
    f = db.execute(
        select(ConversationFolder).where(
            ConversationFolder.id == fid,
            ConversationFolder.space_id == space.id,
            ConversationFolder.user_ref == _user_ref(p),
        )
    ).scalar_one_or_none()
    if f is None:
        raise HTTPException(status_code=404, detail="Dossier introuvable.")
    return f


# --- dossiers ---
@router.get("/folders")
def list_folders(space: Space = Depends(get_space), db: Session = Depends(get_db),
                 principal: Principal = Depends(current_principal)) -> list[dict]:
    rows = db.execute(
        select(ConversationFolder).where(
            ConversationFolder.space_id == space.id,
            ConversationFolder.user_ref == _user_ref(principal),
        ).order_by(ConversationFolder.name)
    ).scalars().all()
    return [_folder_dict(f) for f in rows]


@router.post("/folders")
def create_folder(payload: FolderCreate, space: Space = Depends(get_space),
                  db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    f = ConversationFolder(
        tenant_id=space.tenant_id, space_id=space.id,
        user_ref=_user_ref(principal), name=payload.name.strip(),
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return _folder_dict(f)


@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, space: Space = Depends(get_space),
                  db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    f = _get_folder(db, space, principal, folder_id)
    db.delete(f)
    db.commit()
    return {"deleted": folder_id}


# --- conversations ---
@router.get("")
def list_conversations(space: Space = Depends(get_space), db: Session = Depends(get_db),
                       principal: Principal = Depends(current_principal),
                       archived: bool = Query(default=False)) -> list[dict]:
    rows = db.execute(
        select(Conversation).where(
            Conversation.space_id == space.id,
            Conversation.user_ref == _user_ref(principal),
            Conversation.archived.is_(archived),
        ).order_by(Conversation.updated_at.desc())
    ).scalars().all()
    return [_summary(db, c) for c in rows]


@router.post("")
def create_conversation(payload: ConversationCreate, space: Space = Depends(get_space),
                        db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    if payload.folder_id is not None:
        _get_folder(db, space, principal, payload.folder_id)
    c = Conversation(
        tenant_id=space.tenant_id, space_id=space.id, user_ref=_user_ref(principal),
        title=(payload.title or "Nouvelle conversation").strip() or "Nouvelle conversation",
        folder_id=payload.folder_id,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {**_summary(db, c), "turns": []}


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, space: Space = Depends(get_space),
                     db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    c = _get_conv(db, space, principal, conversation_id)
    return {**_summary(db, c), "turns": [_turn_dict(t) for t in c.turns]}


@router.patch("/{conversation_id}")
def update_conversation(conversation_id: int, payload: ConversationUpdate, space: Space = Depends(get_space),
                        db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    c = _get_conv(db, space, principal, conversation_id)
    data = payload.model_dump(exclude_unset=True)
    if "folder_id" in data:
        if data["folder_id"] is not None:
            _get_folder(db, space, principal, data["folder_id"])
        c.folder_id = data["folder_id"]
    if data.get("title"):
        c.title = data["title"].strip() or c.title
    if data.get("archived") is not None:
        c.archived = data["archived"]
    db.commit()
    db.refresh(c)
    return _summary(db, c)


@router.delete("/{conversation_id}")
def delete_conversation(conversation_id: int, space: Space = Depends(get_space),
                        db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    c = _get_conv(db, space, principal, conversation_id)
    db.delete(c)
    db.commit()
    return {"deleted": conversation_id}


@router.post("/{conversation_id}/turns")
def add_turn(conversation_id: int, payload: SpaceTurnCreate, space: Space = Depends(get_space),
             db: Session = Depends(get_db), principal: Principal = Depends(current_principal)) -> dict:
    c = _get_conv(db, space, principal, conversation_id)
    if not spaces_svc.is_connection_in_space(db, space.id, payload.connection_id):
        raise HTTPException(status_code=404, detail="Cette BDD n'est pas rattachée à l'espace.")
    conn = db.execute(
        select(Connection).where(
            Connection.id == payload.connection_id, Connection.tenant_id == space.tenant_id
        )
    ).scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="Source introuvable.")

    response = chat_svc.answer_question(
        db, conn, payload.question, user_ref=_user_ref(principal),
        run_analysis=payload.run_analysis, deep_analysis=payload.deep_analysis,
        hidden_tables=spaces_svc.hidden_tables(db, space.id, conn.id),
        hidden_columns=spaces_svc.hidden_columns(db, space.id, conn.id),
    )
    resp_dict = jsonable_encoder(response.as_dict())

    ordinal = db.execute(
        select(func.count(ConversationTurn.id)).where(ConversationTurn.conversation_id == c.id)
    ).scalar_one()
    turn = ConversationTurn(
        conversation_id=c.id, ordinal=ordinal, connection_id=conn.id,
        question=payload.question, deep=payload.deep_analysis, response=resp_dict,
    )
    db.add(turn)
    if ordinal == 0 and c.title in ("", "Nouvelle conversation"):
        title = payload.question.strip().replace("\n", " ")
        c.title = (title[:42] + "…") if len(title) > 42 else title
    c.updated_at = func.now()
    db.commit()
    db.refresh(turn)
    return {"turn": _turn_dict(turn), "conversation": _summary(db, c)}
