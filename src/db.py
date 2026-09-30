"""
Persistance PostgreSQL des dossiers, de leurs pièces et du journal d'audit.

Un dossier fige, à sa création, la liste des pièces décidée par le moteur
de règles (rule_engine.py) ainsi que l'empreinte des règles YAML utilisées :
une modification ultérieure des règles ne réécrit jamais un dossier existant.

Cycle de vie d'une pièce (`Document.statut`) :

    pièce à rédiger : a_generer -> en_file -> en_generation -> a_valider -> valide
                                                   |               |
                                                   v               v
                                                erreur          rejete  (-> régénération)

    pièce à fournir : a_obtenir -> valide   (pièce reçue et vérifiée par un humain)
                          |
                          v
                       rejete   (pièce reçue mais non conforme -> a_obtenir à nouveau)

Seul un humain fait passer une pièce à `valide` ou `rejete` (validateur
nommé, horodaté, tracé dans `evenements`). Il n'existe aucun statut de
dépôt : le dépôt reste une démarche manuelle, hors du système.
"""
from __future__ import annotations

import datetime
import os

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://conformite:changer_ce_mot_de_passe@localhost:5432/conformite_dm",
)

STATUTS_A_REDIGER = ("a_generer", "en_file", "en_generation", "erreur", "a_valider", "valide", "rejete")
STATUTS_A_FOURNIR = ("a_obtenir", "valide", "rejete")
STATUTS_EN_COURS = ("en_file", "en_generation")


def maintenant() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Base(DeclarativeBase):
    pass


class Dossier(Base):
    __tablename__ = "dossiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    produit: Mapped[str] = mapped_column(String(300))
    pays_origine: Mapped[str] = mapped_column(String(40))
    pays_destination: Mapped[str] = mapped_column(String(40), default="maroc")
    classe: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fournisseur: Mapped[str | None] = mapped_column(String(300), nullable=True)
    regles_version: Mapped[str] = mapped_column(String(20))
    dossier_sortie: Mapped[str] = mapped_column(String(500))
    cree_par: Mapped[str] = mapped_column(String(120))
    cree_le: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=maintenant)

    documents: Mapped[list[Document]] = relationship(
        back_populates="dossier", order_by="Document.ordre", cascade="all, delete-orphan"
    )
    evenements: Mapped[list[Evenement]] = relationship(
        back_populates="dossier", order_by="Evenement.id", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"), index=True)
    ordre: Mapped[int] = mapped_column(Integer)
    # Copie figée de la décision du moteur de règles
    code: Mapped[str] = mapped_column(String(80))
    nom: Mapped[str] = mapped_column(String(500))
    nature: Mapped[str] = mapped_column(String(20))  # a_rediger | a_fournir
    fourni_par: Mapped[str | None] = mapped_column(String(300), nullable=True)
    consigne_redaction: Mapped[str | None] = mapped_column(Text, nullable=True)
    traduction_requise: Mapped[bool] = mapped_column(Boolean, default=False)
    legalisation_requise: Mapped[bool] = mapped_column(Boolean, default=False)
    origine_regle: Mapped[str] = mapped_column(String(200))
    # Suivi
    statut: Mapped[str] = mapped_column(String(20))
    fichier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    erreur: Mapped[str | None] = mapped_column(Text, nullable=True)
    genere_le: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valide_par: Mapped[str | None] = mapped_column(String(120), nullable=True)
    valide_le: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commentaire: Mapped[str | None] = mapped_column(Text, nullable=True)

    dossier: Mapped[Dossier] = relationship(back_populates="documents")


class Evenement(Base):
    """Journal d'audit : chaque action humaine ou système sur un dossier."""

    __tablename__ = "evenements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dossier_id: Mapped[int] = mapped_column(ForeignKey("dossiers.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    horodatage: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=maintenant)
    acteur: Mapped[str] = mapped_column(String(120))  # nom de la personne, ou "système"
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    dossier: Mapped[Dossier] = relationship(back_populates="evenements")


engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def initialiser_base(moteur=None) -> None:
    """Crée les tables manquantes (pas de migration : à passer sous Alembic
    avant la mise en production si le schéma évolue)."""
    Base.metadata.create_all(moteur or engine)


def journaliser(session, dossier_id: int, acteur: str, action: str, detail: str | None = None, document_id: int | None = None):
    session.add(Evenement(dossier_id=dossier_id, document_id=document_id, acteur=acteur, action=action, detail=detail))
