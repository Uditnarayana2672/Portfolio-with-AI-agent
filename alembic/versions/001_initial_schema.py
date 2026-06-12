"""Complete initial schema — matches ORM models exactly.

Revision ID: 001
Revises:
Create Date: 2025-05-28 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import text

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Custom type for pgvector columns
# ---------------------------------------------------------------------------

class _Vector(sa.types.UserDefinedType):
    """Emit the PostgreSQL `vector` type for pgvector columns."""
    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "vector"


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    conn = op.get_bind()

    # ── extensions ──────────────────────────────────────────────────────────
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # ── enums ────────────────────────────────────────────────────────────────
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE user_role AS ENUM ('admin', 'viewer');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE project_status AS ENUM ('draft', 'published', 'archived');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE content_visibility AS ENUM ('public', 'members_only', 'unlisted');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE blog_status AS ENUM ('draft', 'review', 'published', 'archived');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE resource_type AS ENUM ('image', 'video', 'raw');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE reaction_type AS ENUM ('like', 'love', 'fire', 'clap', 'mind_blown');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE content_type AS ENUM ('blog_post', 'project');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE subscriber_status AS ENUM ('active', 'unsubscribed', 'bounced');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE activity_type AS ENUM (
                'project_created', 'project_updated', 'project_published', 'project_deleted',
                'blog_created', 'blog_updated', 'blog_published', 'blog_archived', 'blog_deleted',
                'media_uploaded', 'media_deleted', 'comment_approved', 'comment_deleted',
                'subscriber_added', 'contact_received', 'jerry_escalation', 'jerry_booking',
                'ai_suggestion_accepted'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE note_type AS ENUM (
                'interest', 'feedback', 'pain_point', 'intent',
                'budget', 'timeline', 'general'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))
    conn.execute(text("""
        DO $$ BEGIN
            CREATE TYPE escalation_trigger AS ENUM (
                'explicit_request', 'negative_sentiment', 'repeated_question',
                'budget_mention', 'urgent_keyword'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
    """))

    # ── tables ───────────────────────────────────────────────────────────────

    # users
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), server_default=text("'admin'::user_role"), nullable=False),
        sa.Column('is_blocked', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='users_pkey'),
        sa.UniqueConstraint('email', name='users_email_key'),
    )
    op.create_index('idx_users_email', 'users', ['email'])
    op.create_index('idx_users_role', 'users', ['role'])

    # blog_categories
    op.create_table(
        'blog_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='blog_categories_pkey'),
        sa.UniqueConstraint('name', name='blog_categories_name_key'),
        sa.UniqueConstraint('slug', name='blog_categories_slug_key'),
    )

    # projects
    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('tech_stack', postgresql.ARRAY(sa.Text()), server_default=text("'{}'::text[]"), nullable=False),
        sa.Column('template_id', sa.Text(), server_default=text("'narrative'::text"), nullable=False),
        sa.Column('status', sa.Text(), server_default=text("'draft'::project_status"), nullable=False),
        sa.Column('visibility', sa.Text(), server_default=text("'public'::content_visibility"), nullable=False),
        sa.Column('is_featured', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('views', sa.Integer(), server_default=text('0'), nullable=False),
        sa.Column('seo', postgresql.JSONB(), server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('github_url', sa.Text(), nullable=True),
        sa.Column('demo_url', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], name='projects_author_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='projects_pkey'),
        sa.UniqueConstraint('slug', name='projects_slug_key'),
    )
    op.create_index('idx_projects_is_featured', 'projects', ['is_featured'])
    op.create_index('idx_projects_published_at', 'projects', ['published_at'])
    op.create_index('idx_projects_slug', 'projects', ['slug'])
    op.create_index('idx_projects_status', 'projects', ['status'])
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_projects_search ON projects USING gin "
        "(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(excerpt, '')))"
    ))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_projects_tech_stack ON projects USING gin (tech_stack)"
    ))

    # project_blocks
    op.create_table(
        'project_blocks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('block_type', sa.Text(), nullable=False),
        sa.Column('position', sa.Integer(), server_default=text('0'), nullable=False),
        sa.Column('config', postgresql.JSONB(), server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='project_blocks_project_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='project_blocks_pkey'),
    )
    op.create_index('idx_project_blocks_project', 'project_blocks', ['project_id'])
    op.create_index('idx_project_blocks_position', 'project_blocks', ['project_id', 'position'])

    # blog_posts
    op.create_table(
        'blog_posts',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('content', postgresql.JSONB(), server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column('tags', postgresql.ARRAY(sa.Text()), server_default=text("'{}'::text[]"), nullable=False),
        sa.Column('status', sa.Text(), server_default=text("'draft'::blog_status"), nullable=False),
        sa.Column('visibility', sa.Text(), server_default=text("'public'::content_visibility"), nullable=False),
        sa.Column('views', sa.Integer(), server_default=text('0'), nullable=False),
        sa.Column('allow_comments', sa.Boolean(), server_default=text('true'), nullable=False),
        sa.Column('seo', postgresql.JSONB(), server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('excerpt', sa.Text(), nullable=True),
        sa.Column('cover_image_url', sa.Text(), nullable=True),
        sa.Column('og_image_url', sa.Text(), nullable=True),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('read_time', sa.Integer(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], name='blog_posts_author_id_fkey'),
        sa.ForeignKeyConstraint(['category_id'], ['blog_categories.id'], name='blog_posts_category_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='blog_posts_pkey'),
        sa.UniqueConstraint('slug', name='blog_posts_slug_key'),
    )
    op.create_index('idx_blog_posts_category', 'blog_posts', ['category_id'])
    op.create_index('idx_blog_posts_published_at', 'blog_posts', ['published_at'])
    op.create_index('idx_blog_posts_slug', 'blog_posts', ['slug'])
    op.create_index('idx_blog_posts_status', 'blog_posts', ['status'])
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_blog_posts_scheduled_at ON blog_posts (scheduled_at) "
        "WHERE scheduled_at IS NOT NULL"
    ))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_blog_posts_search ON blog_posts USING gin "
        "(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(excerpt, '')))"
    ))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_blog_posts_tags ON blog_posts USING gin (tags)"
    ))

    # media_assets
    op.create_table(
        'media_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('resource_type', sa.Text(), server_default=text("'image'::resource_type"), nullable=False),
        sa.Column('folder', sa.Text(), server_default=text("'uncategorized'::text"), nullable=False),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('source_type', sa.Text(), server_default=text("'cloudinary'::text"), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('cloudinary_url', sa.Text(), nullable=True),
        sa.Column('public_id', sa.Text(), nullable=True),
        sa.Column('format', sa.Text(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_name', sa.Text(), nullable=True),
        sa.Column('alt_text', sa.Text(), nullable=True),
        sa.Column('external_id', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('video_title', sa.Text(), nullable=True),
        sa.Column('video_duration_seconds', sa.Integer(), nullable=True),
        sa.Column('file_hash', sa.Text(), nullable=True),
        sa.Column('is_orphan', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.CheckConstraint(
            "source_type = ANY (ARRAY['cloudinary'::text, 'youtube'::text])",
            name='media_assets_source_type_check',
        ),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name='media_assets_uploaded_by_fkey'),
        sa.PrimaryKeyConstraint('id', name='media_assets_pkey'),
        sa.UniqueConstraint('public_id', name='media_assets_public_id_key'),
    )
    op.create_index('idx_media_assets_folder', 'media_assets', ['folder'])
    op.create_index('idx_media_assets_public_id', 'media_assets', ['public_id'])
    op.create_index('idx_media_assets_resource_type', 'media_assets', ['resource_type'])
    op.create_index('idx_media_assets_source_type', 'media_assets', ['source_type'])
    op.create_index('idx_media_assets_file_hash', 'media_assets', ['file_hash'])
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_created_at ON media_assets (created_at DESC)"
    ))
    op.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_media_assets_external_id ON media_assets (external_id) "
        "WHERE external_id IS NOT NULL"
    ))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_search ON media_assets USING gin "
        "(to_tsvector('english', coalesce(file_name, '') || ' ' || coalesce(alt_text, '')))"
    ))
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_media_assets_fname_trgm ON media_assets "
        "USING gin (file_name gin_trgm_ops)"
    ))

    # reactions
    op.create_table(
        'reactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('content_type', sa.Text(), nullable=False),
        sa.Column('content_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reaction_type', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='reactions_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='reactions_pkey'),
    )
    op.create_index('idx_reactions_content', 'reactions', ['content_type', 'content_id'])
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_reactions_user ON reactions (user_id) "
        "WHERE user_id IS NOT NULL"
    ))

    # polls
    op.create_table(
        'polls',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('options', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column('anonymous', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('assigned_to_type', sa.Text(), nullable=True),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='polls_pkey'),
    )
    op.create_index('idx_polls_assigned', 'polls', ['assigned_to_type', 'assigned_to_id'])

    # poll_votes
    op.create_table(
        'poll_votes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('poll_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('option_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('voted_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['poll_id'], ['polls.id'], name='poll_votes_poll_id_fkey'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='poll_votes_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='poll_votes_pkey'),
    )
    op.create_index('idx_poll_votes_poll', 'poll_votes', ['poll_id'])

    # feedback_forms
    op.create_table(
        'feedback_forms',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('fields', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('assigned_to_type', sa.Text(), nullable=True),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='feedback_forms_pkey'),
    )

    # feedback_submissions
    op.create_table(
        'feedback_submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('form_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('responses', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['form_id'], ['feedback_forms.id'], name='feedback_submissions_form_id_fkey'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='feedback_submissions_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='feedback_submissions_pkey'),
    )
    op.create_index('idx_feedback_submissions_form', 'feedback_submissions', ['form_id'])

    # comments
    op.create_table(
        'comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('blog_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_approved', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('author_name', sa.Text(), nullable=True),
        sa.Column('author_email', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['blog_id'], ['blog_posts.id'], name='comments_blog_id_fkey'),
        sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], name='comments_parent_id_fkey'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='comments_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='comments_pkey'),
    )
    op.create_index('idx_comments_blog', 'comments', ['blog_id'])
    op.create_index('idx_comments_approved', 'comments', ['blog_id', 'is_approved'])
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments (parent_id) "
        "WHERE parent_id IS NOT NULL"
    ))

    # newsletter_subscribers
    op.create_table(
        'newsletter_subscribers',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('topics', postgresql.ARRAY(sa.Text()), server_default=text("'{}'::text[]"), nullable=False),
        sa.Column('status', sa.Text(), server_default=text("'active'::subscriber_status"), nullable=False),
        sa.Column('subscribed_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('unsubscribe_token', sa.Text(), server_default=text("encode(gen_random_bytes(32), 'hex'::text)"), nullable=True),
        sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='newsletter_subscribers_pkey'),
        sa.UniqueConstraint('email', name='newsletter_subscribers_email_key'),
        sa.UniqueConstraint('unsubscribe_token', name='newsletter_subscribers_unsubscribe_token_key'),
    )
    op.create_index('idx_subscribers_email', 'newsletter_subscribers', ['email'])
    op.create_index('idx_subscribers_status', 'newsletter_subscribers', ['status'])

    # contact_messages
    op.create_table(
        'contact_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('subject', sa.Text(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('read', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('attachment_url', sa.Text(), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='contact_messages_pkey'),
    )
    op.create_index('idx_contact_messages_created', 'contact_messages', ['created_at'])
    op.create_index('idx_contact_messages_read', 'contact_messages', ['read'])

    # page_views
    op.create_table(
        'page_views',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('viewed_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('referrer', sa.Text(), nullable=True),
        sa.Column('country', sa.CHAR(1), nullable=True),
        sa.Column('user_agent_hash', sa.Text(), nullable=True),
        sa.Column('session_id', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='page_views_pkey'),
    )
    op.create_index('idx_page_views_path', 'page_views', ['path'])
    op.create_index('idx_page_views_viewed_at', 'page_views', ['viewed_at'])

    # activity_log
    op.create_table(
        'activity_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('action_type', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('entity_type', sa.Text(), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('entity_title', sa.Text(), nullable=True),
        sa.Column('performed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), server_default=text("'{}'::jsonb"), nullable=True),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], name='activity_log_performed_by_fkey'),
        sa.PrimaryKeyConstraint('id', name='activity_log_pkey'),
    )
    op.create_index('idx_activity_log_action', 'activity_log', ['action_type'])
    op.create_index('idx_activity_log_created', 'activity_log', ['created_at'])
    op.create_index('idx_activity_log_entity', 'activity_log', ['entity_type', 'entity_id'])

    # admin_style_profile
    op.create_table(
        'admin_style_profile',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('admin_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('examples', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=False),
        sa.Column('sample_count', sa.Integer(), server_default=text('0'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('style_vector', _Vector(), nullable=True),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], name='admin_style_profile_admin_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='admin_style_profile_pkey'),
        sa.UniqueConstraint('admin_user_id', name='admin_style_profile_admin_user_id_key'),
    )

    # assistant_sessions
    op.create_table(
        'assistant_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('visitor_id', sa.Text(), nullable=False),
        sa.Column('message_count', sa.Integer(), server_default=text('0'), nullable=False),
        sa.Column('has_escalation', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('has_booking', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('session_token', sa.Text(), server_default=text("encode(gen_random_bytes(32), 'hex'::text)"), nullable=True),
        sa.PrimaryKeyConstraint('id', name='assistant_sessions_pkey'),
        sa.UniqueConstraint('session_token', name='assistant_sessions_session_token_key'),
    )
    op.create_index('idx_assistant_sessions_created', 'assistant_sessions', ['created_at'])
    op.create_index('idx_assistant_sessions_visitor', 'assistant_sessions', ['visitor_id'])

    # assistant_messages
    op.create_table(
        'assistant_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('suggested_options', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=True),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_buttons', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=True),
        sa.CheckConstraint(
            "role = ANY (ARRAY['user'::text, 'assistant'::text])",
            name='assistant_messages_role_check',
        ),
        sa.ForeignKeyConstraint(['session_id'], ['assistant_sessions.id'], name='assistant_messages_session_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='assistant_messages_pkey'),
    )
    op.create_index('idx_assistant_messages_session', 'assistant_messages', ['session_id'])
    op.create_index('idx_assistant_messages_created', 'assistant_messages', ['session_id', 'created_at'])

    # visitor_graph_nodes
    op.create_table(
        'visitor_graph_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.Text(), nullable=False),
        sa.Column('entity_value', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('confidence', sa.Float(), server_default=text('1.0'), nullable=True),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='visitor_graph_nodes_visitor_session_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='visitor_graph_nodes_pkey'),
    )
    op.create_index('idx_vgn_session', 'visitor_graph_nodes', ['visitor_session_id'])

    # visitor_graph_edges
    op.create_table(
        'visitor_graph_edges',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('source_node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relationship_type', sa.Text(), nullable=False),
        sa.Column('target_node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['source_node_id'], ['visitor_graph_nodes.id'], name='visitor_graph_edges_source_node_id_fkey'),
        sa.ForeignKeyConstraint(['target_node_id'], ['visitor_graph_nodes.id'], name='visitor_graph_edges_target_node_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='visitor_graph_edges_pkey'),
    )
    op.create_index('idx_vge_source', 'visitor_graph_edges', ['source_node_id'])
    op.create_index('idx_vge_target', 'visitor_graph_edges', ['target_node_id'])

    # jerry_voice_profile
    op.create_table(
        'jerry_voice_profile',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('profile_text', sa.Text(), nullable=False),
        sa.Column('style_preferences', postgresql.JSONB(), server_default=text("'{}'::jsonb"), nullable=False),
        sa.Column('version', sa.Integer(), server_default=text('1'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name='jerry_voice_profile_pkey'),
    )

    # jerry_style_corpus
    op.create_table(
        'jerry_style_corpus',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('source_type', sa.Text(), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('embedding_vector', _Vector(), nullable=True),
        sa.Column('context_tag', sa.Text(), nullable=True),
        sa.Column('pii_scrubbed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='jerry_style_corpus_pkey'),
    )
    op.create_index('idx_jsc_context', 'jerry_style_corpus', ['context_tag'])
    op.create_index('idx_jsc_source', 'jerry_style_corpus', ['source_type'])

    # jerry_pricing_kb
    op.create_table(
        'jerry_pricing_kb',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('service_type', sa.Text(), nullable=False),
        sa.Column('price_range_low', sa.Numeric(), nullable=False),
        sa.Column('price_range_high', sa.Numeric(), nullable=False),
        sa.Column('currency', sa.CHAR(3), server_default=text("'USD'::bpchar"), nullable=False),
        sa.Column('timeline_weeks_min', sa.Integer(), nullable=False),
        sa.Column('timeline_weeks_max', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=text('true'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id', name='jerry_pricing_kb_pkey'),
    )

    # jerry_notes
    op.create_table(
        'jerry_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_id', sa.Text(), nullable=False),
        sa.Column('note_text', sa.Text(), nullable=False),
        sa.Column('note_type', sa.Text(), server_default=text("'general'::note_type"), nullable=False),
        sa.Column('is_starred', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('is_feedback', sa.Boolean(), server_default=text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('source_message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('conversation_snapshot', postgresql.JSONB(), server_default=text("'[]'::jsonb"), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['source_message_id'], ['assistant_messages.id'], name='jerry_notes_source_message_id_fkey'),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='jerry_notes_visitor_session_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='jerry_notes_pkey'),
    )
    op.create_index('idx_jerry_notes_created', 'jerry_notes', ['created_at'])
    op.create_index('idx_jerry_notes_session', 'jerry_notes', ['visitor_session_id'])
    op.create_index('idx_jerry_notes_starred', 'jerry_notes', ['is_starred'])
    op.create_index('idx_jerry_notes_type', 'jerry_notes', ['note_type'])

    # jerry_admin_sessions
    op.create_table(
        'jerry_admin_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('admin_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], name='jerry_admin_sessions_admin_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='jerry_admin_sessions_pkey'),
    )

    # jerry_escalations
    op.create_table(
        'jerry_escalations',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_type', sa.Text(), nullable=False),
        sa.Column('message_excerpt', sa.Text(), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='jerry_escalations_visitor_session_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='jerry_escalations_pkey'),
    )
    op.create_index('idx_jerry_escalations_session', 'jerry_escalations', ['visitor_session_id'])
    op.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_jerry_escalations_unresolved ON jerry_escalations (resolved_at) "
        "WHERE resolved_at IS NULL"
    ))

    # jerry_bookings
    op.create_table(
        'jerry_bookings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=text('gen_random_uuid()'), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_email', sa.Text(), nullable=False),
        sa.Column('visitor_name', sa.Text(), nullable=False),
        sa.Column('slot_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('slot_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=text('now()'), nullable=False),
        sa.Column('topic', sa.Text(), nullable=True),
        sa.Column('google_event_id', sa.Text(), nullable=True),
        sa.Column('calendar_link', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='jerry_bookings_visitor_session_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='jerry_bookings_pkey'),
    )
    op.create_index('idx_jerry_bookings_slot', 'jerry_bookings', ['slot_start'])


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    conn = op.get_bind()

    op.drop_table('jerry_bookings')
    op.drop_table('jerry_escalations')
    op.drop_table('jerry_admin_sessions')
    op.drop_table('jerry_notes')
    op.drop_table('jerry_pricing_kb')
    op.drop_table('jerry_style_corpus')
    op.drop_table('jerry_voice_profile')
    op.drop_table('visitor_graph_edges')
    op.drop_table('visitor_graph_nodes')
    op.drop_table('assistant_messages')
    op.drop_table('assistant_sessions')
    op.drop_table('admin_style_profile')
    op.drop_table('activity_log')
    op.drop_table('page_views')
    op.drop_table('contact_messages')
    op.drop_table('newsletter_subscribers')
    op.drop_table('comments')
    op.drop_table('feedback_submissions')
    op.drop_table('feedback_forms')
    op.drop_table('poll_votes')
    op.drop_table('polls')
    op.drop_table('reactions')
    op.drop_table('media_assets')
    op.drop_table('blog_posts')
    op.drop_table('project_blocks')
    op.drop_table('projects')
    op.drop_table('blog_categories')
    op.drop_table('users')

    conn.execute(text("DROP TYPE IF EXISTS escalation_trigger"))
    conn.execute(text("DROP TYPE IF EXISTS note_type"))
    conn.execute(text("DROP TYPE IF EXISTS activity_type"))
    conn.execute(text("DROP TYPE IF EXISTS subscriber_status"))
    conn.execute(text("DROP TYPE IF EXISTS content_type"))
    conn.execute(text("DROP TYPE IF EXISTS reaction_type"))
    conn.execute(text("DROP TYPE IF EXISTS resource_type"))
    conn.execute(text("DROP TYPE IF EXISTS blog_status"))
    conn.execute(text("DROP TYPE IF EXISTS content_visibility"))
    conn.execute(text("DROP TYPE IF EXISTS project_status"))
    conn.execute(text("DROP TYPE IF EXISTS user_role"))
