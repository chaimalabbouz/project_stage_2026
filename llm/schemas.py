"""
schemas.py
----------
Modèles Pydantic pour valider et typer les réponses JSON du LLM.
Chaque schéma correspond à une structure attendue dans le planning.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Schémas de base
# ---------------------------------------------------------------------------

class FileItem(BaseModel):
    """Représente un fichier à générer dans le projet React."""

    path: str = Field(..., description="Chemin relatif depuis src/ ex: components/Header.jsx")
    type: Literal["component", "page", "hook", "context", "util", "style", "config"] = Field(
        ..., description="Type du fichier"
    )
    component_name: str = Field(..., description="Nom du composant ou export principal")
    depends_on: list[str] = Field(
        default_factory=list,
        description="Liste des chemins de fichiers dont ce fichier dépend",
    )
    reuses_figma_component: str | None = Field(
        default=None,
        description="ID du composant Figma réutilisable correspondant, si applicable",
    )
    description: str = Field(..., description="Description courte du rôle de ce fichier")
    props: list[str] = Field(
        default_factory=list,
        description="Liste des props principales attendues (pour les composants)",
    )


class FolderItem(BaseModel):
    """Représente un dossier dans la structure du projet."""

    path: str = Field(..., description="Chemin relatif depuis la racine du projet")
    purpose: str = Field(..., description="Rôle de ce dossier dans le projet")


class RouteItem(BaseModel):
    """Représente une route React Router."""

    path: str = Field(..., description="Chemin URL ex: /products")
    page_component: str = Field(..., description="Nom du composant de page")
    file_path: str = Field(..., description="Chemin vers le fichier de la page")


class DependencyItem(BaseModel):
    """Représente une dépendance npm nécessaire."""

    package: str = Field(..., description="Nom du package npm")
    reason: str = Field(..., description="Pourquoi cette dépendance est nécessaire")


# ---------------------------------------------------------------------------
# Schéma principal du planning
# ---------------------------------------------------------------------------

class ProjectPlanning(BaseModel):
    """
    Planning complet du projet React à générer depuis le design Figma.
    C'est la structure que le LLM doit retourner.
    """

    project_name: str = Field(..., description="Nom du projet React")
    description: str = Field(..., description="Description générale du site/app")

    folders: list[FolderItem] = Field(
        ..., description="Liste de tous les dossiers à créer"
    )
    files: list[FileItem] = Field(
        ..., description="Liste de tous les fichiers à générer"
    )
    routes: list[RouteItem] = Field(
        default_factory=list,
        description="Routes React Router si plusieurs pages",
    )
    dependencies: list[DependencyItem] = Field(
        default_factory=list,
        description="Dépendances npm nécessaires",
    )

    generation_order: list[str] = Field(
        default_factory=list,
        description="Ordre recommandé de génération des fichiers (chemins)",
    )

    notes: str | None = Field(
        default=None,
        description="Notes ou observations importantes sur le design",
    )

    @field_validator("files")
    @classmethod
    def files_must_not_be_empty(cls, v: list[FileItem]) -> list[FileItem]:
        if not v:
            raise ValueError("Le planning doit contenir au moins un fichier.")
        return v

    @field_validator("folders")
    @classmethod
    def folders_must_not_be_empty(cls, v: list[FolderItem]) -> list[FolderItem]:
        if not v:
            raise ValueError("Le planning doit contenir au moins un dossier.")
        return v


# ---------------------------------------------------------------------------
# Schéma pour le résumé cumulatif (rolling context)
# ---------------------------------------------------------------------------

class PartialPlanningSummary(BaseModel):
    """
    Résumé compact d'un planning partiel, utilisé comme contexte cumulatif
    entre les appels LLM successifs (rolling context).
    """

    components_identified: list[str] = Field(
        default_factory=list,
        description="Noms des composants React déjà identifiés",
    )
    pages_identified: list[str] = Field(
        default_factory=list,
        description="Noms des pages déjà identifiées",
    )
    folders_identified: list[str] = Field(
        default_factory=list,
        description="Dossiers déjà planifiés",
    )
    key_observations: list[str] = Field(
        default_factory=list,
        description="Observations importantes sur le design jusqu'ici",
    )

    @classmethod
    def from_planning(cls, planning: ProjectPlanning) -> "PartialPlanningSummary":
        """Crée un résumé compact depuis un planning partiel."""
        components = [
            f.component_name
            for f in planning.files
            if f.type == "component"
        ]
        pages = [
            f.component_name
            for f in planning.files
            if f.type == "page"
        ]
        folders = [fold.path for fold in planning.folders]

        return cls(
            components_identified=components,
            pages_identified=pages,
            folders_identified=folders,
            key_observations=[planning.notes] if planning.notes else [],
        )