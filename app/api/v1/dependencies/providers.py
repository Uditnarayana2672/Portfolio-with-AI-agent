"""Dependency providers — the request-scoped composition root.

This is where the onion's outer layer wires concrete infrastructure
(repositories, external services) into application use cases. Endpoints depend
on these providers via FastAPI's `Depends`, so they never construct
infrastructure themselves.

As features are added, define one provider per use case here, e.g.:

    def get_upload_media(
        db: Session = Depends(get_db),
        storage: ImageStorage = Depends(get_image_storage),
    ) -> UploadMedia:
        repo = SqlAlchemyMediaAssetRepository(db)
        return UploadMedia(repo=repo, storage=storage)
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.application.dtos.blog import BlogSettings
from app.application.use_cases.activity.list_recent_activity import ListRecentActivity
from app.application.interfaces.site_services import CaptchaVerifier, EmailSender, SiteDeployer
from app.application.use_cases.inbox.newsletter_send import PrepareNewsletterSend
from app.application.use_cases.public_site.blogs import PublicBlog
from app.application.use_cases.public_site.interactions import (
    Engagement,
    Newsletter,
    PublicComments,
    PublicPolls,
    SubmitContactMessage,
)
from app.application.use_cases.public_site.projects import ListProjectSlugs, ListPublicProjects
from app.application.use_cases.public_site.site_builds import SiteBuilds
from app.domain.repositories.inbox_repository import InboxRepository
from app.domain.repositories.public_site_repository import PublicSiteRepository
from app.infrastructure.external.site_services import CloudflareDeployer, ResendEmailSender, TurnstileVerifier
from app.infrastructure.persistence.repositories.inbox_repository import SqlAlchemyInboxRepository
from app.infrastructure.persistence.repositories.public_site_repository import SqlAlchemyPublicSiteRepository
from app.infrastructure.persistence.repositories.site_build_repository import SqlAlchemySiteBuildRepository
from app.application.use_cases.portfolio.portfolio_content import GetPortfolioContent, UpdatePortfolioContent
from app.application.interfaces.image_storage import ImageStorage
from app.application.use_cases.blog.editor_support import GetEditorConfig, ResolveEmbed, SearchLinkTargets
from app.application.use_cases.blog.manager import BulkBlogAction, GetBlogStats, ListBlogPosts, UnarchiveBlogPost
from app.application.use_cases.blog.post_workflow import BlogPostWorkflow
from app.application.use_cases.blog.posts import (
    CheckBlogSlug,
    CreateBlogPost,
    DeleteBlogPost,
    GetBlogPost,
    UpdateBlogPost,
)
from app.application.use_cases.blog.preview import GetBlogPreview
from app.application.use_cases.blog.publishing import (
    DiscardBlogChanges,
    GetBlogChecklist,
    PublishBlogPost,
    PublishDuePosts,
    ScheduleBlogPost,
    UnpublishBlogPost,
    UnscheduleBlogPost,
)
from app.application.use_cases.blog.revisions import (
    CreateBlogRevision,
    GetBlogRevision,
    ListBlogRevisions,
    RestoreBlogRevision,
)
from app.application.use_cases.blog.taxonomy import CreateBlogCategory, ListBlogCategories, ListBlogTags
from app.application.interfaces.url_fetcher import UrlFetcher
from app.application.interfaces.video_metadata import VideoMetadataProvider
from app.application.use_cases.media.bulk_delete_media import BulkDeleteMedia
from app.application.use_cases.media.bulk_update_media import BulkUpdateMedia
from app.application.use_cases.media.delete_media import DeleteMedia
from app.application.use_cases.media.get_media_asset import GetMediaAsset
from app.application.use_cases.media.get_media_stats import GetMediaStats
from app.application.use_cases.media.get_media_usage import GetMediaUsage
from app.application.use_cases.media.import_url_media import ImportUrlMedia
from app.application.use_cases.media.list_media import ListMedia
from app.application.use_cases.media.update_media import UpdateMedia
from app.application.use_cases.media.upload_media import UploadMedia
from app.application.use_cases.projects.add_block import AddBlock
from app.application.use_cases.projects.bulk_action import BulkAction
from app.application.use_cases.projects.check_slug_availability import CheckSlugAvailability
from app.application.use_cases.projects.create_project import CreateProject
from app.application.use_cases.projects.duplicate_project import DuplicateProject
from app.application.use_cases.projects.delete_block import DeleteBlock
from app.application.use_cases.projects.delete_project import DeleteProject
from app.application.interfaces.block_config_validator import BlockConfigValidator
from app.application.use_cases.projects.get_project import GetProject
from app.application.use_cases.projects.get_public_project import GetPublicProject
from app.application.use_cases.projects.react_to_project import ReactToProject
from app.application.use_cases.projects.get_status_counts import GetStatusCounts
from app.application.use_cases.projects.toggle_feature import ToggleFeature
from app.application.use_cases.projects.reorder_blocks import ReorderBlocks
from app.application.use_cases.projects.update_block import UpdateBlock
from app.application.use_cases.forms.list_forms import ListForms
from app.application.use_cases.projects.list_projects import ListProjects
from app.application.use_cases.projects.publish_project import PublishProject
from app.application.use_cases.projects.update_project import UpdateProject
from app.api.v1.schemas.block_config import PydanticBlockConfigValidator
from app.domain.repositories.activity_log_repository import ActivityLogRepository
from app.domain.repositories.blog_category_repository import BlogCategoryRepository
from app.domain.repositories.blog_list_repository import BlogListRepository
from app.domain.repositories.blog_post_repository import BlogPostRepository
from app.domain.repositories.block_repository import BlockRepository
from app.domain.repositories.form_repository import FormRepository
from app.domain.repositories.media_asset_repository import MediaAssetRepository
from app.domain.repositories.project_repository import ProjectRepository
from app.infrastructure.config import settings
from app.infrastructure.external.cloudinary_storage import CloudinaryImageStorage
from app.infrastructure.external.safe_url_fetcher import SafeHttpUrlFetcher
from app.infrastructure.external.youtube_metadata import YouTubeMetadataProvider
from app.infrastructure.persistence.database import SessionLocal, get_db
from app.infrastructure.persistence.repositories.portfolio_content_repository import (
    SqlAlchemyPortfolioContentRepository,
)
from app.infrastructure.persistence.repositories.activity_log_repository import (
    SqlAlchemyActivityLogRepository,
)
from app.infrastructure.persistence.repositories.media_asset_repository import (
    SqlAlchemyMediaAssetRepository,
)
from app.infrastructure.persistence.repositories.blog_category_repository import (
    SqlAlchemyBlogCategoryRepository,
)
from app.infrastructure.persistence.repositories.blog_list_repository import SqlAlchemyBlogListRepository
from app.infrastructure.persistence.repositories.blog_post_repository import (
    SqlAlchemyBlogPostRepository,
)
from app.infrastructure.rendering.tiptap_renderer import TipTapHtmlRenderer
from app.infrastructure.persistence.repositories.block_repository import (
    SqlAlchemyBlockRepository,
)
from app.infrastructure.persistence.repositories.form_repository import StaticFormRepository
from app.infrastructure.persistence.repositories.project_repository import (
    SqlAlchemyProjectRepository,
)


def get_image_storage() -> ImageStorage:
    """Provide the configured image storage adapter (Cloudinary)."""
    return CloudinaryImageStorage()


def get_media_repository(db: Session = Depends(get_db)) -> MediaAssetRepository:
    """Bind the SQLAlchemy media repository to the request's DB session."""
    return SqlAlchemyMediaAssetRepository(db)


def get_activity_repository(db: Session = Depends(get_db)) -> ActivityLogRepository:
    """Bind the SQLAlchemy activity-log repository to the request's DB session."""
    return SqlAlchemyActivityLogRepository(db)


def get_list_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> ListMedia:
    return ListMedia(repo=repo)


def get_media_asset(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> GetMediaAsset:
    return GetMediaAsset(repo=repo)


def get_media_usage(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> GetMediaUsage:
    return GetMediaUsage(repo=repo)


def get_media_stats(
    repo: MediaAssetRepository = Depends(get_media_repository),
) -> GetMediaStats:
    # Quota/plan come from config (the PLUS plan's 2.25 GB by default); used
    # bytes are summed from the DB inside the use case.
    return GetMediaStats(
        repo=repo,
        quota_bytes=settings.CLOUDINARY_QUOTA_BYTES,
        plan=settings.CLOUDINARY_PLAN,
    )


def get_upload_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    storage: ImageStorage = Depends(get_image_storage),
) -> UploadMedia:
    return UploadMedia(repo=repo, activity=activity, storage=storage)


def get_update_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    storage: ImageStorage = Depends(get_image_storage),
) -> UpdateMedia:
    return UpdateMedia(repo=repo, storage=storage)


def get_delete_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    storage: ImageStorage = Depends(get_image_storage),
) -> DeleteMedia:
    return DeleteMedia(repo=repo, activity=activity, storage=storage)


def get_bulk_delete_media(
    delete_media: DeleteMedia = Depends(get_delete_media),
) -> BulkDeleteMedia:
    return BulkDeleteMedia(delete_media=delete_media)


def get_bulk_update_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    update_media: UpdateMedia = Depends(get_update_media),
) -> BulkUpdateMedia:
    return BulkUpdateMedia(repo=repo, update_media=update_media)


def get_url_fetcher() -> UrlFetcher:
    """Provide the SSRF-hardened URL fetcher (timeout/redirect caps from config)."""
    return SafeHttpUrlFetcher()


def get_video_metadata() -> VideoMetadataProvider:
    return YouTubeMetadataProvider()


def get_import_url_media(
    repo: MediaAssetRepository = Depends(get_media_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    storage: ImageStorage = Depends(get_image_storage),
    fetcher: UrlFetcher = Depends(get_url_fetcher),
    video_metadata: VideoMetadataProvider = Depends(get_video_metadata),
) -> ImportUrlMedia:
    return ImportUrlMedia(
        repo=repo,
        activity=activity,
        storage=storage,
        fetcher=fetcher,
        video_metadata=video_metadata,
    )


# ── forms ─────────────────────────────────────────────────────────────────────


def get_form_repository() -> FormRepository:
    return StaticFormRepository()


def get_list_forms(
    repo: FormRepository = Depends(get_form_repository),
) -> ListForms:
    return ListForms(repo=repo)


# ── projects ──────────────────────────────────────────────────────────────────


def get_project_repository(db: Session = Depends(get_db)) -> ProjectRepository:
    """Bind the SQLAlchemy project repository to the request's DB session."""
    return SqlAlchemyProjectRepository(db)


def get_list_projects(
    repo: ProjectRepository = Depends(get_project_repository),
) -> ListProjects:
    return ListProjects(repo=repo)


def get_publish_project(
    repo: ProjectRepository = Depends(get_project_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> PublishProject:
    return PublishProject(repo=repo, activity=activity)


def get_check_slug_availability(
    repo: ProjectRepository = Depends(get_project_repository),
) -> CheckSlugAvailability:
    return CheckSlugAvailability(repo=repo)


def get_create_project(
    repo: ProjectRepository = Depends(get_project_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> CreateProject:
    return CreateProject(repo=repo, activity=activity)


def get_get_project(
    repo: ProjectRepository = Depends(get_project_repository),
) -> GetProject:
    return GetProject(repo=repo)


def get_get_public_project(
    repo: ProjectRepository = Depends(get_project_repository),
) -> GetPublicProject:
    return GetPublicProject(repo=repo)


def get_react_to_project(
    repo: ProjectRepository = Depends(get_project_repository),
) -> ReactToProject:
    return ReactToProject(repo=repo)


def get_update_project(
    repo: ProjectRepository = Depends(get_project_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> UpdateProject:
    return UpdateProject(repo=repo, activity=activity)


def get_delete_project(
    repo: ProjectRepository = Depends(get_project_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> DeleteProject:
    return DeleteProject(repo=repo, activity=activity)


def get_toggle_feature(
    repo: ProjectRepository = Depends(get_project_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> ToggleFeature:
    return ToggleFeature(repo=repo, activity=activity)


# ── blocks ────────────────────────────────────────────────────────────────────


def get_block_repository(db: Session = Depends(get_db)) -> BlockRepository:
    return SqlAlchemyBlockRepository(db)


def get_duplicate_project(
    project_repo: ProjectRepository = Depends(get_project_repository),
    block_repo: BlockRepository = Depends(get_block_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> DuplicateProject:
    return DuplicateProject(project_repo=project_repo, block_repo=block_repo, activity=activity)


def get_add_block(
    project_repo: ProjectRepository = Depends(get_project_repository),
    block_repo: BlockRepository = Depends(get_block_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> AddBlock:
    return AddBlock(project_repo=project_repo, block_repo=block_repo, activity=activity)


def get_delete_block(
    project_repo: ProjectRepository = Depends(get_project_repository),
    block_repo: BlockRepository = Depends(get_block_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> DeleteBlock:
    return DeleteBlock(project_repo=project_repo, block_repo=block_repo, activity=activity)


def get_block_config_validator() -> BlockConfigValidator:
    """Provide the Pydantic-backed block config validator (UpdateBlock)."""
    return PydanticBlockConfigValidator()


def get_update_block(
    block_repo: BlockRepository = Depends(get_block_repository),
    config_validator: BlockConfigValidator = Depends(get_block_config_validator),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> UpdateBlock:
    return UpdateBlock(
        block_repo=block_repo,
        config_validator=config_validator,
        activity=activity,
    )


def get_reorder_blocks(
    project_repo: ProjectRepository = Depends(get_project_repository),
    block_repo: BlockRepository = Depends(get_block_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
) -> ReorderBlocks:
    return ReorderBlocks(project_repo=project_repo, block_repo=block_repo, activity=activity)


def get_get_status_counts(
    repo: ProjectRepository = Depends(get_project_repository),
) -> GetStatusCounts:
    return GetStatusCounts(repo=repo)


def get_bulk_action(
    repo: ProjectRepository = Depends(get_project_repository),
) -> BulkAction:
    return BulkAction(repo=repo)


# ── Blog editor ──────────────────────────────────────────────────────────────


def get_blog_settings() -> BlogSettings:
    return BlogSettings(
        site_url=settings.SITE_URL,
        portfolio_url=settings.PORTFOLIO_SITE_URL,
        timezone=settings.ADMIN_TIMEZONE,
    )


def get_blog_post_repository(db: Session = Depends(get_db)) -> BlogPostRepository:
    return SqlAlchemyBlogPostRepository(db)


def get_blog_category_repository(db: Session = Depends(get_db)) -> BlogCategoryRepository:
    return SqlAlchemyBlogCategoryRepository(db)


def get_blog_workflow(
    repo: BlogPostRepository = Depends(get_blog_post_repository),
    categories: BlogCategoryRepository = Depends(get_blog_category_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    blog_settings: BlogSettings = Depends(get_blog_settings),
) -> BlogPostWorkflow:
    return BlogPostWorkflow(
        repo=repo,
        categories=categories,
        renderer=TipTapHtmlRenderer(),
        activity=activity,
        settings=blog_settings,
    )


def get_editor_config(blog_settings: BlogSettings = Depends(get_blog_settings)) -> GetEditorConfig:
    return GetEditorConfig(blog_settings)


def get_create_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> CreateBlogPost:
    return CreateBlogPost(wf)


def get_get_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> GetBlogPost:
    return GetBlogPost(wf)


def get_update_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> UpdateBlogPost:
    return UpdateBlogPost(wf)


def get_delete_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> DeleteBlogPost:
    return DeleteBlogPost(wf)


def get_check_blog_slug(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> CheckBlogSlug:
    return CheckBlogSlug(wf)


def get_blog_checklist(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> GetBlogChecklist:
    return GetBlogChecklist(wf)


def get_publish_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> PublishBlogPost:
    return PublishBlogPost(wf)


def get_schedule_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> ScheduleBlogPost:
    return ScheduleBlogPost(wf)


def get_unschedule_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> UnscheduleBlogPost:
    return UnscheduleBlogPost(wf)


def get_unpublish_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> UnpublishBlogPost:
    return UnpublishBlogPost(wf)


def get_discard_blog_changes(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> DiscardBlogChanges:
    return DiscardBlogChanges(wf)


def get_blog_preview(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> GetBlogPreview:
    return GetBlogPreview(wf)


def get_create_blog_revision(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> CreateBlogRevision:
    return CreateBlogRevision(wf)


def get_list_blog_revisions(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> ListBlogRevisions:
    return ListBlogRevisions(wf)


def get_get_blog_revision(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> GetBlogRevision:
    return GetBlogRevision(wf)


def get_restore_blog_revision(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> RestoreBlogRevision:
    return RestoreBlogRevision(wf)


def get_list_blog_categories(
    repo: BlogCategoryRepository = Depends(get_blog_category_repository),
) -> ListBlogCategories:
    return ListBlogCategories(repo)


def get_create_blog_category(
    repo: BlogCategoryRepository = Depends(get_blog_category_repository),
) -> CreateBlogCategory:
    return CreateBlogCategory(repo)


def get_list_blog_tags(repo: BlogPostRepository = Depends(get_blog_post_repository)) -> ListBlogTags:
    return ListBlogTags(repo)


def get_resolve_embed() -> ResolveEmbed:
    return ResolveEmbed()


def get_search_link_targets(
    repo: BlogPostRepository = Depends(get_blog_post_repository),
) -> SearchLinkTargets:
    return SearchLinkTargets(repo)


def get_publish_due_posts(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> PublishDuePosts:
    return PublishDuePosts(wf)


# ── Blog Manager ─────────────────────────────────────────────────────────────


def get_blog_list_repository(db: Session = Depends(get_db)) -> BlogListRepository:
    return SqlAlchemyBlogListRepository(db)


def get_list_blog_posts(repo: BlogListRepository = Depends(get_blog_list_repository)) -> ListBlogPosts:
    return ListBlogPosts(repo)


def get_blog_stats(
    repo: BlogListRepository = Depends(get_blog_list_repository),
    blog_settings: BlogSettings = Depends(get_blog_settings),
) -> GetBlogStats:
    return GetBlogStats(repo, blog_settings)


def get_bulk_blog_action(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> BulkBlogAction:
    return BulkBlogAction(wf)


def get_unarchive_blog_post(wf: BlogPostWorkflow = Depends(get_blog_workflow)) -> UnarchiveBlogPost:
    return UnarchiveBlogPost(wf)


def get_list_recent_activity(db: Session = Depends(get_db)) -> ListRecentActivity:
    return ListRecentActivity(SqlAlchemyActivityLogRepository(db))


def get_get_portfolio_content(db: Session = Depends(get_db)) -> GetPortfolioContent:
    return GetPortfolioContent(SqlAlchemyPortfolioContentRepository(db))


def get_update_portfolio_content(db: Session = Depends(get_db)) -> UpdatePortfolioContent:
    return UpdatePortfolioContent(
        repo=SqlAlchemyPortfolioContentRepository(db),
        activity=SqlAlchemyActivityLogRepository(db),
    )


# ── public site ──────────────────────────────────────────────────────────────


def get_public_site_repository(db: Session = Depends(get_db)) -> PublicSiteRepository:
    return SqlAlchemyPublicSiteRepository(db)


def get_inbox_repository(db: Session = Depends(get_db)) -> InboxRepository:
    return SqlAlchemyInboxRepository(db)


def get_email_sender() -> EmailSender:
    return ResendEmailSender(settings.RESEND_API_KEY, settings.EMAIL_FROM)


def get_captcha() -> CaptchaVerifier:
    return TurnstileVerifier(settings.TURNSTILE_SECRET_KEY)


def _site_deployer() -> SiteDeployer:
    return CloudflareDeployer({
        "portfolio": settings.DEPLOY_HOOK_PORTFOLIO,
        "lighthouse": settings.DEPLOY_HOOK_LIGHTHOUSE,
    })


def get_list_public_projects(repo: PublicSiteRepository = Depends(get_public_site_repository)) -> ListPublicProjects:
    return ListPublicProjects(repo)


def get_list_project_slugs(repo: PublicSiteRepository = Depends(get_public_site_repository)) -> ListProjectSlugs:
    return ListProjectSlugs(repo)


def get_public_blog(
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    workflow: BlogPostWorkflow = Depends(get_blog_workflow),
) -> PublicBlog:
    return PublicBlog(repo, workflow)


def get_engagement(repo: PublicSiteRepository = Depends(get_public_site_repository)) -> Engagement:
    return Engagement(repo)


def get_public_polls(repo: PublicSiteRepository = Depends(get_public_site_repository)) -> PublicPolls:
    return PublicPolls(repo)


def get_public_comments(
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    captcha: CaptchaVerifier = Depends(get_captcha),
) -> PublicComments:
    return PublicComments(repo, captcha)


def get_submit_contact_message(
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    captcha: CaptchaVerifier = Depends(get_captcha),
    email: EmailSender = Depends(get_email_sender),
) -> SubmitContactMessage:
    return SubmitContactMessage(repo, activity, captcha, email, settings.CONTACT_NOTIFY_EMAIL)


def get_newsletter(
    repo: PublicSiteRepository = Depends(get_public_site_repository),
    activity: ActivityLogRepository = Depends(get_activity_repository),
    captcha: CaptchaVerifier = Depends(get_captcha),
    email: EmailSender = Depends(get_email_sender),
) -> Newsletter:
    return Newsletter(repo, activity, captcha, email, settings.SITE_URL)


def get_prepare_newsletter_send(
    repo: InboxRepository = Depends(get_inbox_repository),
    workflow: BlogPostWorkflow = Depends(get_blog_workflow),
) -> PrepareNewsletterSend:
    return PrepareNewsletterSend(repo, workflow)


def get_site_builds(db: Session = Depends(get_db)) -> SiteBuilds:
    return SiteBuilds(SqlAlchemySiteBuildRepository(db), _site_deployer())


def run_flush_site_builds() -> None:
    """One scheduler tick outside a request: ask the host for any due rebuilds."""
    db = SessionLocal()
    try:
        SiteBuilds(SqlAlchemySiteBuildRepository(db), _site_deployer()).flush()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_publish_due_posts() -> None:
    """One scheduler tick outside a request: own session, commit on success.
    Wired into the in-process scheduler by app/main.py."""
    db = SessionLocal()
    try:
        workflow = BlogPostWorkflow(
            repo=SqlAlchemyBlogPostRepository(db),
            categories=SqlAlchemyBlogCategoryRepository(db),
            renderer=TipTapHtmlRenderer(),
            activity=SqlAlchemyActivityLogRepository(db),
            settings=get_blog_settings(),
        )
        PublishDuePosts(workflow).execute()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
