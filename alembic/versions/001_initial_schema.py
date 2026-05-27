"""Initial schema from portfolio-old

Revision ID: 001
Revises:
Create Date: 2025-05-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import Enum

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    user_role = Enum('admin', 'viewer', name='user_role')
    user_role.create(op.get_bind(), checkfirst=True)

    project_status = Enum('draft', 'published', 'archived', name='project_status')
    project_status.create(op.get_bind(), checkfirst=True)

    content_visibility = Enum('public', 'members_only', 'unlisted', name='content_visibility')
    content_visibility.create(op.get_bind(), checkfirst=True)

    blog_status = Enum('draft', 'review', 'published', 'archived', name='blog_status')
    blog_status.create(op.get_bind(), checkfirst=True)

    resource_type = Enum('image', 'video', 'raw', name='resource_type')
    resource_type.create(op.get_bind(), checkfirst=True)

    reaction_type = Enum('like', 'love', 'fire', 'clap', 'mind_blown', name='reaction_type')
    reaction_type.create(op.get_bind(), checkfirst=True)

    content_type = Enum('blog_post', 'project', name='content_type')
    content_type.create(op.get_bind(), checkfirst=True)

    subscriber_status = Enum('active', 'unsubscribed', 'bounced', name='subscriber_status')
    subscriber_status.create(op.get_bind(), checkfirst=True)

    activity_type = Enum(
        'project_created', 'project_updated', 'project_published', 'project_deleted',
        'blog_created', 'blog_updated', 'blog_published', 'blog_archived', 'blog_deleted',
        'media_uploaded', 'media_deleted', 'comment_approved', 'comment_deleted',
        'subscriber_added', 'contact_received', 'jerry_escalation', 'jerry_booking',
        'ai_suggestion_accepted', name='activity_type'
    )
    activity_type.create(op.get_bind(), checkfirst=True)

    note_type = Enum('interest', 'feedback', 'pain_point', 'intent', 'budget', 'timeline', 'general', name='note_type')
    note_type.create(op.get_bind(), checkfirst=True)

    escalation_trigger = Enum('explicit_request', 'negative_sentiment', 'repeated_question', 'budget_mention', 'urgent_keyword', name='escalation_trigger')
    escalation_trigger.create(op.get_bind(), checkfirst=True)

    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('avatar_url', sa.String(), nullable=True),
        sa.Column('role', user_role, server_default="'admin'::user_role", nullable=False),
        sa.Column('is_blocked', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    # Create blog_categories table
    op.create_table('blog_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug')
    )

    # Create projects table
    op.create_table('projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('excerpt', sa.String(), nullable=True),
        sa.Column('thumbnail_url', sa.String(), nullable=True),
        sa.Column('tech_stack', postgresql.ARRAY(sa.String()), server_default="'{}'::text[]", nullable=False),
        sa.Column('template_id', sa.String(), server_default="'narrative'::text", nullable=False),
        sa.Column('github_url', sa.String(), nullable=True),
        sa.Column('demo_url', sa.String(), nullable=True),
        sa.Column('status', project_status, server_default="'draft'::project_status", nullable=False),
        sa.Column('visibility', content_visibility, server_default="'public'::content_visibility", nullable=False),
        sa.Column('is_featured', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('views', sa.Integer(), server_default='0', nullable=False),
        sa.Column('seo', postgresql.JSONB(astext_type=sa.Text()), server_default="'{}'::jsonb", nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    # Create project_blocks table
    op.create_table('project_blocks',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('block_type', sa.String(), nullable=False),
        sa.Column('position', sa.Integer(), server_default='0', nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), server_default="'{}'::jsonb", nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create blog_posts table
    op.create_table('blog_posts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('slug', sa.String(), nullable=False),
        sa.Column('content', postgresql.JSONB(astext_type=sa.Text()), server_default="'{}'::jsonb", nullable=False),
        sa.Column('excerpt', sa.String(), nullable=True),
        sa.Column('cover_image_url', sa.String(), nullable=True),
        sa.Column('og_image_url', sa.String(), nullable=True),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('tags', postgresql.ARRAY(sa.String()), server_default="'{}'::text[]", nullable=False),
        sa.Column('status', blog_status, server_default="'draft'::blog_status", nullable=False),
        sa.Column('visibility', content_visibility, server_default="'public'::content_visibility", nullable=False),
        sa.Column('read_time', sa.Integer(), nullable=True),
        sa.Column('views', sa.Integer(), server_default='0', nullable=False),
        sa.Column('allow_comments', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('seo', postgresql.JSONB(astext_type=sa.Text()), server_default="'{}'::jsonb", nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['blog_categories.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
    )

    # Create media_assets table
    op.create_table('media_assets',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cloudinary_url', sa.String(), nullable=False),
        sa.Column('public_id', sa.String(), nullable=False),
        sa.Column('resource_type', resource_type, server_default="'image'::resource_type", nullable=False),
        sa.Column('format', sa.String(), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('file_name', sa.String(), nullable=True),
        sa.Column('folder', sa.String(), server_default="'uncategorized'::text", nullable=False),
        sa.Column('alt_text', sa.String(), nullable=True),
        sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id')
    )

    # Create reactions table
    op.create_table('reactions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('content_type', content_type, nullable=False),
        sa.Column('content_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('reaction_type', reaction_type, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create polls table
    op.create_table('polls',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('question', sa.String(), nullable=False),
        sa.Column('options', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('assigned_to_type', content_type, nullable=True),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('anonymous', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create poll_votes table
    op.create_table('poll_votes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('poll_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('option_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('voted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['poll_id'], ['polls.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create feedback_forms table
    op.create_table('feedback_forms',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('fields', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('assigned_to_type', content_type, nullable=True),
        sa.Column('assigned_to_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create feedback_submissions table
    op.create_table('feedback_submissions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('form_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('responses', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['form_id'], ['feedback_forms.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create comments table
    op.create_table('comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('blog_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('parent_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('author_name', sa.String(), nullable=True),
        sa.Column('author_email', sa.String(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_approved', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['blog_id'], ['blog_posts.id'], ),
        sa.ForeignKeyConstraint(['parent_id'], ['comments.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create newsletter_subscribers table
    op.create_table('newsletter_subscribers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('topics', postgresql.ARRAY(sa.String()), server_default="'{}'::text[]", nullable=False),
        sa.Column('status', subscriber_status, server_default="'active'::subscriber_status", nullable=False),
        sa.Column('unsubscribe_token', sa.String(), nullable=True),
        sa.Column('subscribed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('unsubscribed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
        sa.UniqueConstraint('unsubscribe_token')
    )

    # Create contact_messages table
    op.create_table('contact_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('attachment_url', sa.String(), nullable=True),
        sa.Column('read', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create page_views table
    op.create_table('page_views',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('referrer', sa.String(), nullable=True),
        sa.Column('country', sa.String(length=2), nullable=True),
        sa.Column('user_agent_hash', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('viewed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create activity_log table
    op.create_table('activity_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('action_type', activity_type, nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=True),
        sa.Column('entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('entity_title', sa.String(), nullable=True),
        sa.Column('performed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default="'{}'::jsonb", nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['performed_by'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create admin_style_profile table
    op.create_table('admin_style_profile',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('admin_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('style_vector', sa.String(), nullable=True),
        sa.Column('examples', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('sample_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('admin_user_id')
    )

    # Create assistant_sessions table
    op.create_table('assistant_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_id', sa.String(), nullable=False),
        sa.Column('session_token', sa.String(), nullable=True),
        sa.Column('message_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('has_escalation', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('has_booking', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_active_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_token')
    )

    # Create assistant_messages table
    op.create_table('assistant_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('suggested_options', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('question_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_buttons', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name='assistant_messages_role_check'),
        sa.ForeignKeyConstraint(['session_id'], ['assistant_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create visitor_graph_nodes table
    op.create_table('visitor_graph_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.String(), nullable=False),
        sa.Column('entity_value', sa.String(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create visitor_graph_edges table
    op.create_table('visitor_graph_edges',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relationship_type', sa.String(), nullable=False),
        sa.Column('target_node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['source_node_id'], ['visitor_graph_nodes.id'], ),
        sa.ForeignKeyConstraint(['target_node_id'], ['visitor_graph_nodes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_voice_profile table
    op.create_table('jerry_voice_profile',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('profile_text', sa.Text(), nullable=False),
        sa.Column('style_preferences', postgresql.JSONB(astext_type=sa.Text()), server_default="'{}'::jsonb", nullable=False),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_style_corpus table
    op.create_table('jerry_style_corpus',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_type', sa.String(), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('embedding_vector', sa.String(), nullable=True),
        sa.Column('context_tag', sa.String(), nullable=True),
        sa.Column('pii_scrubbed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_pricing_kb table
    op.create_table('jerry_pricing_kb',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('service_type', sa.String(), nullable=False),
        sa.Column('price_range_low', sa.Numeric(), nullable=False),
        sa.Column('price_range_high', sa.Numeric(), nullable=False),
        sa.Column('currency', sa.String(length=3), server_default="'USD'", nullable=False),
        sa.Column('timeline_weeks_min', sa.Integer(), nullable=False),
        sa.Column('timeline_weeks_max', sa.Integer(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_notes table
    op.create_table('jerry_notes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_id', sa.String(), nullable=False),
        sa.Column('source_message_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('note_text', sa.Text(), nullable=False),
        sa.Column('note_type', note_type, server_default="'general'::note_type", nullable=False),
        sa.Column('is_starred', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_feedback', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('conversation_snapshot', postgresql.JSONB(astext_type=sa.Text()), server_default="'[]'::jsonb", nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['source_message_id'], ['assistant_messages.id'], ),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_admin_sessions table
    op.create_table('jerry_admin_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('admin_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['admin_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_escalations table
    op.create_table('jerry_escalations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trigger_type', escalation_trigger, nullable=False),
        sa.Column('message_excerpt', sa.Text(), nullable=False),
        sa.Column('notified_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )

    # Create jerry_bookings table
    op.create_table('jerry_bookings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('visitor_email', sa.String(), nullable=False),
        sa.Column('visitor_name', sa.String(), nullable=False),
        sa.Column('topic', sa.String(), nullable=True),
        sa.Column('slot_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('slot_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('google_event_id', sa.String(), nullable=True),
        sa.Column('calendar_link', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop tables
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

    # Drop enums
    sa.Enum('admin', 'viewer', name='user_role').drop(op.get_bind(), checkfirst=True)
    sa.Enum('draft', 'published', 'archived', name='project_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum('public', 'members_only', 'unlisted', name='content_visibility').drop(op.get_bind(), checkfirst=True)
    sa.Enum('draft', 'review', 'published', 'archived', name='blog_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum('image', 'video', 'raw', name='resource_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum('like', 'love', 'fire', 'clap', 'mind_blown', name='reaction_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum('blog_post', 'project', name='content_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum('active', 'unsubscribed', 'bounced', name='subscriber_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum('project_created', 'project_updated', 'project_published', 'project_deleted', 'blog_created', 'blog_updated', 'blog_published', 'blog_archived', 'blog_deleted', 'media_uploaded', 'media_deleted', 'comment_approved', 'comment_deleted', 'subscriber_added', 'contact_received', 'jerry_escalation', 'jerry_booking', 'ai_suggestion_accepted', name='activity_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum('interest', 'feedback', 'pain_point', 'intent', 'budget', 'timeline', 'general', name='note_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum('explicit_request', 'negative_sentiment', 'repeated_question', 'budget_mention', 'urgent_keyword', name='escalation_trigger').drop(op.get_bind(), checkfirst=True)
