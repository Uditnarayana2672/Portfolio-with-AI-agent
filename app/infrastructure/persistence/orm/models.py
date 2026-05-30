from typing import Any, Optional
import datetime
import decimal
import enum
import uuid

from pgvector.sqlalchemy.vector import VECTOR
from sqlalchemy import ARRAY, Boolean, CHAR, CheckConstraint, DateTime, Double, Enum, ForeignKeyConstraint, Index, Integer, Numeric, PrimaryKeyConstraint, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.database import Base


class ActivityType(str, enum.Enum):
    PROJECT_CREATED = 'project_created'
    PROJECT_UPDATED = 'project_updated'
    PROJECT_PUBLISHED = 'project_published'
    PROJECT_DELETED = 'project_deleted'
    BLOG_CREATED = 'blog_created'
    BLOG_UPDATED = 'blog_updated'
    BLOG_PUBLISHED = 'blog_published'
    BLOG_ARCHIVED = 'blog_archived'
    BLOG_DELETED = 'blog_deleted'
    MEDIA_UPLOADED = 'media_uploaded'
    MEDIA_DELETED = 'media_deleted'
    COMMENT_APPROVED = 'comment_approved'
    COMMENT_DELETED = 'comment_deleted'
    SUBSCRIBER_ADDED = 'subscriber_added'
    CONTACT_RECEIVED = 'contact_received'
    JERRY_ESCALATION = 'jerry_escalation'
    JERRY_BOOKING = 'jerry_booking'
    AI_SUGGESTION_ACCEPTED = 'ai_suggestion_accepted'


class BlogStatus(str, enum.Enum):
    DRAFT = 'draft'
    REVIEW = 'review'
    PUBLISHED = 'published'
    ARCHIVED = 'archived'


class ContentType(str, enum.Enum):
    BLOG_POST = 'blog_post'
    PROJECT = 'project'


class ContentVisibility(str, enum.Enum):
    PUBLIC = 'public'
    MEMBERS_ONLY = 'members_only'
    UNLISTED = 'unlisted'


class EscalationTrigger(str, enum.Enum):
    EXPLICIT_REQUEST = 'explicit_request'
    NEGATIVE_SENTIMENT = 'negative_sentiment'
    REPEATED_QUESTION = 'repeated_question'
    BUDGET_MENTION = 'budget_mention'
    URGENT_KEYWORD = 'urgent_keyword'


class NoteType(str, enum.Enum):
    INTEREST = 'interest'
    FEEDBACK = 'feedback'
    PAIN_POINT = 'pain_point'
    INTENT = 'intent'
    BUDGET = 'budget'
    TIMELINE = 'timeline'
    GENERAL = 'general'


class ProjectStatus(str, enum.Enum):
    DRAFT = 'draft'
    PUBLISHED = 'published'
    ARCHIVED = 'archived'


class ReactionType(str, enum.Enum):
    LIKE = 'like'
    LOVE = 'love'
    FIRE = 'fire'
    CLAP = 'clap'
    MIND_BLOWN = 'mind_blown'


class ResourceType(str, enum.Enum):
    IMAGE = 'image'
    VIDEO = 'video'
    RAW = 'raw'


class SubscriberStatus(str, enum.Enum):
    ACTIVE = 'active'
    UNSUBSCRIBED = 'unsubscribed'
    BOUNCED = 'bounced'


class UserRole(str, enum.Enum):
    ADMIN = 'admin'
    VIEWER = 'viewer'


class AssistantSessions(Base):
    __tablename__ = 'assistant_sessions'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='assistant_sessions_pkey'),
        UniqueConstraint('session_token', name='assistant_sessions_session_token_key'),
        Index('idx_assistant_sessions_created', 'created_at'),
        Index('idx_assistant_sessions_visitor', 'visitor_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    visitor_id: Mapped[str] = mapped_column(Text, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    has_escalation: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    has_booking: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    last_active_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    session_token: Mapped[Optional[str]] = mapped_column(Text, server_default=text("encode(gen_random_bytes(32), 'hex'::text)"))

    assistant_messages: Mapped[list['AssistantMessages']] = relationship('AssistantMessages', back_populates='session')
    jerry_bookings: Mapped[list['JerryBookings']] = relationship('JerryBookings', back_populates='visitor_session')
    jerry_escalations: Mapped[list['JerryEscalations']] = relationship('JerryEscalations', back_populates='visitor_session')
    visitor_graph_nodes: Mapped[list['VisitorGraphNodes']] = relationship('VisitorGraphNodes', back_populates='visitor_session')
    jerry_notes: Mapped[list['JerryNotes']] = relationship('JerryNotes', back_populates='visitor_session')


class BlogCategories(Base):
    __tablename__ = 'blog_categories'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='blog_categories_pkey'),
        UniqueConstraint('name', name='blog_categories_name_key'),
        UniqueConstraint('slug', name='blog_categories_slug_key')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    description: Mapped[Optional[str]] = mapped_column(Text)

    blog_posts: Mapped[list['BlogPosts']] = relationship('BlogPosts', back_populates='category')


class ContactMessages(Base):
    __tablename__ = 'contact_messages'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='contact_messages_pkey'),
        Index('idx_contact_messages_created', 'created_at'),
        Index('idx_contact_messages_read', 'read')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    attachment_url: Mapped[Optional[str]] = mapped_column(Text)
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class FeedbackForms(Base):
    __tablename__ = 'feedback_forms'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='feedback_forms_pkey'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    assigned_to_type: Mapped[Optional[ContentType]] = mapped_column(Enum(ContentType, values_callable=lambda cls: [member.value for member in cls], name='content_type'))
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)

    feedback_submissions: Mapped[list['FeedbackSubmissions']] = relationship('FeedbackSubmissions', back_populates='form')


class JerryPricingKb(Base):
    __tablename__ = 'jerry_pricing_kb'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='jerry_pricing_kb_pkey'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    service_type: Mapped[str] = mapped_column(Text, nullable=False)
    price_range_low: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    price_range_high: Mapped[decimal.Decimal] = mapped_column(Numeric, nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'USD'::bpchar"))
    timeline_weeks_min: Mapped[int] = mapped_column(Integer, nullable=False)
    timeline_weeks_max: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    notes: Mapped[Optional[str]] = mapped_column(Text)


class JerryStyleCorpus(Base):
    __tablename__ = 'jerry_style_corpus'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='jerry_style_corpus_pkey'),
        Index('idx_jsc_context', 'context_tag'),
        Index('idx_jsc_source', 'source_type')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    embedding_vector: Mapped[Optional[Any]] = mapped_column(VECTOR)
    context_tag: Mapped[Optional[str]] = mapped_column(Text)
    pii_scrubbed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class JerryVoiceProfile(Base):
    __tablename__ = 'jerry_voice_profile'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='jerry_voice_profile_pkey'),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    profile_text: Mapped[str] = mapped_column(Text, nullable=False)
    style_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('1'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))


class NewsletterSubscribers(Base):
    __tablename__ = 'newsletter_subscribers'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='newsletter_subscribers_pkey'),
        UniqueConstraint('email', name='newsletter_subscribers_email_key'),
        UniqueConstraint('unsubscribe_token', name='newsletter_subscribers_unsubscribe_token_key'),
        Index('idx_subscribers_email', 'email'),
        Index('idx_subscribers_status', 'status')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]"))
    status: Mapped[SubscriberStatus] = mapped_column(Enum(SubscriberStatus, values_callable=lambda cls: [member.value for member in cls], name='subscriber_status'), nullable=False, server_default=text("'active'::subscriber_status"))
    subscribed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    name: Mapped[Optional[str]] = mapped_column(Text)
    unsubscribe_token: Mapped[Optional[str]] = mapped_column(Text, server_default=text("encode(gen_random_bytes(32), 'hex'::text)"))
    unsubscribed_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))


class PageViews(Base):
    __tablename__ = 'page_views'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='page_views_pkey'),
        Index('idx_page_views_path', 'path'),
        Index('idx_page_views_viewed_at', 'viewed_at')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    path: Mapped[str] = mapped_column(Text, nullable=False)
    viewed_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    referrer: Mapped[Optional[str]] = mapped_column(Text)
    country: Mapped[Optional[str]] = mapped_column(CHAR(1))
    user_agent_hash: Mapped[Optional[str]] = mapped_column(Text)
    session_id: Mapped[Optional[str]] = mapped_column(Text)


class Polls(Base):
    __tablename__ = 'polls'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='polls_pkey'),
        Index('idx_polls_assigned', 'assigned_to_type', 'assigned_to_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    anonymous: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    assigned_to_type: Mapped[Optional[ContentType]] = mapped_column(Enum(ContentType, values_callable=lambda cls: [member.value for member in cls], name='content_type'))
    assigned_to_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    poll_votes: Mapped[list['PollVotes']] = relationship('PollVotes', back_populates='poll')


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        PrimaryKeyConstraint('id', name='users_pkey'),
        UniqueConstraint('email', name='users_email_key'),
        Index('idx_users_email', 'email'),
        Index('idx_users_role', 'role')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    email: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, values_callable=lambda cls: [member.value for member in cls], name='user_role'), nullable=False, server_default=text("'admin'::user_role"))
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    avatar_url: Mapped[Optional[str]] = mapped_column(Text)
    last_login_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    activity_log: Mapped[list['ActivityLog']] = relationship('ActivityLog', back_populates='users')
    admin_style_profile: Mapped['AdminStyleProfile'] = relationship('AdminStyleProfile', uselist=False, back_populates='admin_user')
    blog_posts: Mapped[list['BlogPosts']] = relationship('BlogPosts', back_populates='author')
    feedback_submissions: Mapped[list['FeedbackSubmissions']] = relationship('FeedbackSubmissions', back_populates='user')
    jerry_admin_sessions: Mapped[list['JerryAdminSessions']] = relationship('JerryAdminSessions', back_populates='admin_user')
    media_assets: Mapped[list['MediaAssets']] = relationship('MediaAssets', back_populates='users')
    poll_votes: Mapped[list['PollVotes']] = relationship('PollVotes', back_populates='user')
    projects: Mapped[list['Projects']] = relationship('Projects', back_populates='author')
    reactions: Mapped[list['Reactions']] = relationship('Reactions', back_populates='user')
    comments: Mapped[list['Comments']] = relationship('Comments', back_populates='user')


class ActivityLog(Base):
    __tablename__ = 'activity_log'
    __table_args__ = (
        ForeignKeyConstraint(['performed_by'], ['users.id'], name='activity_log_performed_by_fkey'),
        PrimaryKeyConstraint('id', name='activity_log_pkey'),
        Index('idx_activity_log_action', 'action_type'),
        Index('idx_activity_log_created', 'created_at'),
        Index('idx_activity_log_entity', 'entity_type', 'entity_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    action_type: Mapped[ActivityType] = mapped_column(Enum(ActivityType, values_callable=lambda cls: [member.value for member in cls], name='activity_type'), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    entity_type: Mapped[Optional[str]] = mapped_column(Text)
    entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    entity_title: Mapped[Optional[str]] = mapped_column(Text)
    performed_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    metadata_: Mapped[Optional[dict]] = mapped_column('metadata', JSONB, server_default=text("'{}'::jsonb"))

    users: Mapped[Optional['Users']] = relationship('Users', back_populates='activity_log')


class AdminStyleProfile(Base):
    __tablename__ = 'admin_style_profile'
    __table_args__ = (
        ForeignKeyConstraint(['admin_user_id'], ['users.id'], name='admin_style_profile_admin_user_id_fkey'),
        PrimaryKeyConstraint('id', name='admin_style_profile_pkey'),
        UniqueConstraint('admin_user_id', name='admin_style_profile_admin_user_id_key')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    admin_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    examples: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    style_vector: Mapped[Optional[Any]] = mapped_column(VECTOR)

    admin_user: Mapped['Users'] = relationship('Users', back_populates='admin_style_profile')


class AssistantMessages(Base):
    __tablename__ = 'assistant_messages'
    __table_args__ = (
        CheckConstraint("role = ANY (ARRAY['user'::text, 'assistant'::text])", name='assistant_messages_role_check'),
        ForeignKeyConstraint(['session_id'], ['assistant_sessions.id'], name='assistant_messages_session_id_fkey'),
        PrimaryKeyConstraint('id', name='assistant_messages_pkey'),
        Index('idx_assistant_messages_created', 'session_id', 'created_at'),
        Index('idx_assistant_messages_session', 'session_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    suggested_options: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    action_buttons: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))

    session: Mapped['AssistantSessions'] = relationship('AssistantSessions', back_populates='assistant_messages')
    jerry_notes: Mapped[list['JerryNotes']] = relationship('JerryNotes', back_populates='source_message')


class BlogPosts(Base):
    __tablename__ = 'blog_posts'
    __table_args__ = (
        ForeignKeyConstraint(['author_id'], ['users.id'], name='blog_posts_author_id_fkey'),
        ForeignKeyConstraint(['category_id'], ['blog_categories.id'], name='blog_posts_category_id_fkey'),
        PrimaryKeyConstraint('id', name='blog_posts_pkey'),
        UniqueConstraint('slug', name='blog_posts_slug_key'),
        Index('idx_blog_posts_category', 'category_id'),
        Index('idx_blog_posts_published_at', 'published_at'),
        Index('idx_blog_posts_scheduled_at', 'scheduled_at', postgresql_where='(scheduled_at IS NOT NULL)'),
        Index('idx_blog_posts_search', postgresql_using='gin'),
        Index('idx_blog_posts_slug', 'slug'),
        Index('idx_blog_posts_status', 'status'),
        Index('idx_blog_posts_tags', 'tags', postgresql_using='gin')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]"))
    status: Mapped[BlogStatus] = mapped_column(Enum(BlogStatus, values_callable=lambda cls: [member.value for member in cls], name='blog_status'), nullable=False, server_default=text("'draft'::blog_status"))
    visibility: Mapped[ContentVisibility] = mapped_column(Enum(ContentVisibility, values_callable=lambda cls: [member.value for member in cls], name='content_visibility'), nullable=False, server_default=text("'public'::content_visibility"))
    views: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    allow_comments: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('true'))
    seo: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    cover_image_url: Mapped[Optional[str]] = mapped_column(Text)
    og_image_url: Mapped[Optional[str]] = mapped_column(Text)
    category_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    read_time: Mapped[Optional[int]] = mapped_column(Integer)
    scheduled_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    author: Mapped['Users'] = relationship('Users', back_populates='blog_posts')
    category: Mapped[Optional['BlogCategories']] = relationship('BlogCategories', back_populates='blog_posts')
    comments: Mapped[list['Comments']] = relationship('Comments', back_populates='blog')


class FeedbackSubmissions(Base):
    __tablename__ = 'feedback_submissions'
    __table_args__ = (
        ForeignKeyConstraint(['form_id'], ['feedback_forms.id'], name='feedback_submissions_form_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.id'], name='feedback_submissions_user_id_fkey'),
        PrimaryKeyConstraint('id', name='feedback_submissions_pkey'),
        Index('idx_feedback_submissions_form', 'form_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    form_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    responses: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    submitted_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    session_id: Mapped[Optional[str]] = mapped_column(Text)

    form: Mapped['FeedbackForms'] = relationship('FeedbackForms', back_populates='feedback_submissions')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='feedback_submissions')


class JerryAdminSessions(Base):
    __tablename__ = 'jerry_admin_sessions'
    __table_args__ = (
        ForeignKeyConstraint(['admin_user_id'], ['users.id'], name='jerry_admin_sessions_admin_user_id_fkey'),
        PrimaryKeyConstraint('id', name='jerry_admin_sessions_pkey')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    admin_user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    admin_user: Mapped['Users'] = relationship('Users', back_populates='jerry_admin_sessions')


class JerryBookings(Base):
    __tablename__ = 'jerry_bookings'
    __table_args__ = (
        ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='jerry_bookings_visitor_session_id_fkey'),
        PrimaryKeyConstraint('id', name='jerry_bookings_pkey'),
        Index('idx_jerry_bookings_slot', 'slot_start')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    visitor_session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    visitor_email: Mapped[str] = mapped_column(Text, nullable=False)
    visitor_name: Mapped[str] = mapped_column(Text, nullable=False)
    slot_start: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    slot_end: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    topic: Mapped[Optional[str]] = mapped_column(Text)
    google_event_id: Mapped[Optional[str]] = mapped_column(Text)
    calendar_link: Mapped[Optional[str]] = mapped_column(Text)

    visitor_session: Mapped['AssistantSessions'] = relationship('AssistantSessions', back_populates='jerry_bookings')


class JerryEscalations(Base):
    __tablename__ = 'jerry_escalations'
    __table_args__ = (
        ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='jerry_escalations_visitor_session_id_fkey'),
        PrimaryKeyConstraint('id', name='jerry_escalations_pkey'),
        Index('idx_jerry_escalations_session', 'visitor_session_id'),
        Index('idx_jerry_escalations_unresolved', 'resolved_at', postgresql_where='(resolved_at IS NULL)')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    visitor_session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    trigger_type: Mapped[EscalationTrigger] = mapped_column(Enum(EscalationTrigger, values_callable=lambda cls: [member.value for member in cls], name='escalation_trigger'), nullable=False)
    message_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    notified_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    visitor_session: Mapped['AssistantSessions'] = relationship('AssistantSessions', back_populates='jerry_escalations')


class MediaAssets(Base):
    __tablename__ = 'media_assets'
    __table_args__ = (
        CheckConstraint("source_type = ANY (ARRAY['cloudinary'::text, 'youtube'::text])", name='media_assets_source_type_check'),
        ForeignKeyConstraint(['uploaded_by'], ['users.id'], name='media_assets_uploaded_by_fkey'),
        PrimaryKeyConstraint('id', name='media_assets_pkey'),
        UniqueConstraint('public_id', name='media_assets_public_id_key'),
        Index('idx_media_assets_folder', 'folder'),
        Index('idx_media_assets_public_id', 'public_id'),
        Index('idx_media_assets_resource_type', 'resource_type'),
        Index('idx_media_assets_search', postgresql_using='gin'),
        Index('idx_media_assets_source_type', 'source_type'),
        Index('uq_media_assets_external_id', 'external_id', postgresql_where='(external_id IS NOT NULL)', unique=True),
        Index('idx_media_assets_file_hash', 'file_hash'),
        Index('idx_media_assets_created_at', text('created_at DESC')),
        Index('idx_media_assets_fname_trgm', 'file_name', postgresql_using='gin', postgresql_ops={'file_name': 'gin_trgm_ops'})
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    resource_type: Mapped[ResourceType] = mapped_column(Enum(ResourceType, values_callable=lambda cls: [member.value for member in cls], name='resource_type'), nullable=False, server_default=text("'image'::resource_type"))
    folder: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'uncategorized'::text"))
    uploaded_by: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    source_type: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'cloudinary'::text"))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    cloudinary_url: Mapped[Optional[str]] = mapped_column(Text)
    public_id: Mapped[Optional[str]] = mapped_column(Text)
    format: Mapped[Optional[str]] = mapped_column(Text)
    width: Mapped[Optional[int]] = mapped_column(Integer)
    height: Mapped[Optional[int]] = mapped_column(Integer)
    file_size: Mapped[Optional[int]] = mapped_column(Integer)
    file_name: Mapped[Optional[str]] = mapped_column(Text)
    alt_text: Mapped[Optional[str]] = mapped_column(Text)
    external_id: Mapped[Optional[str]] = mapped_column(Text)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text)
    video_title: Mapped[Optional[str]] = mapped_column(Text)
    video_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    # SHA-256 of the uploaded binary, for duplicate detection. NULL for assets
    # imported by URL (e.g. YouTube) where we never see the raw bytes.
    file_hash: Mapped[Optional[str]] = mapped_column(Text)
    # Flagged TRUE by the nightly cleanup job when the Cloudinary asset is gone
    # but the DB row remains (shown as a "404 / DB record only" card in the grid).
    is_orphan: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))

    users: Mapped['Users'] = relationship('Users', back_populates='media_assets')


class PollVotes(Base):
    __tablename__ = 'poll_votes'
    __table_args__ = (
        ForeignKeyConstraint(['poll_id'], ['polls.id'], name='poll_votes_poll_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.id'], name='poll_votes_user_id_fkey'),
        PrimaryKeyConstraint('id', name='poll_votes_pkey'),
        Index('idx_poll_votes_poll', 'poll_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    poll_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    option_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    voted_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    session_id: Mapped[Optional[str]] = mapped_column(Text)

    poll: Mapped['Polls'] = relationship('Polls', back_populates='poll_votes')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='poll_votes')


class Projects(Base):
    __tablename__ = 'projects'
    __table_args__ = (
        ForeignKeyConstraint(['author_id'], ['users.id'], name='projects_author_id_fkey'),
        PrimaryKeyConstraint('id', name='projects_pkey'),
        UniqueConstraint('slug', name='projects_slug_key'),
        Index('idx_projects_is_featured', 'is_featured'),
        Index('idx_projects_published_at', 'published_at'),
        Index('idx_projects_search', postgresql_using='gin'),
        Index('idx_projects_slug', 'slug'),
        Index('idx_projects_status', 'status'),
        Index('idx_projects_tech_stack', 'tech_stack', postgresql_using='gin')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    tech_stack: Mapped[list[str]] = mapped_column(ARRAY(Text()), nullable=False, server_default=text("'{}'::text[]"))
    template_id: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'narrative'::text"))
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus, values_callable=lambda cls: [member.value for member in cls], name='project_status'), nullable=False, server_default=text("'draft'::project_status"))
    visibility: Mapped[ContentVisibility] = mapped_column(Enum(ContentVisibility, values_callable=lambda cls: [member.value for member in cls], name='content_visibility'), nullable=False, server_default=text("'public'::content_visibility"))
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    views: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    seo: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    excerpt: Mapped[Optional[str]] = mapped_column(Text)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text)
    github_url: Mapped[Optional[str]] = mapped_column(Text)
    demo_url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    author: Mapped['Users'] = relationship('Users', back_populates='projects')
    project_blocks: Mapped[list['ProjectBlocks']] = relationship('ProjectBlocks', back_populates='project')


class Reactions(Base):
    __tablename__ = 'reactions'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.id'], name='reactions_user_id_fkey'),
        PrimaryKeyConstraint('id', name='reactions_pkey'),
        Index('idx_reactions_content', 'content_type', 'content_id'),
        Index('idx_reactions_user', 'user_id', postgresql_where='(user_id IS NOT NULL)')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    content_type: Mapped[ContentType] = mapped_column(Enum(ContentType, values_callable=lambda cls: [member.value for member in cls], name='content_type'), nullable=False)
    content_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    reaction_type: Mapped[ReactionType] = mapped_column(Enum(ReactionType, values_callable=lambda cls: [member.value for member in cls], name='reaction_type'), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    session_id: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional['Users']] = relationship('Users', back_populates='reactions')


class VisitorGraphNodes(Base):
    __tablename__ = 'visitor_graph_nodes'
    __table_args__ = (
        ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='visitor_graph_nodes_visitor_session_id_fkey'),
        PrimaryKeyConstraint('id', name='visitor_graph_nodes_pkey'),
        Index('idx_vgn_session', 'visitor_session_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    visitor_session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    confidence: Mapped[Optional[float]] = mapped_column(Double(53), server_default=text('1.0'))

    visitor_session: Mapped['AssistantSessions'] = relationship('AssistantSessions', back_populates='visitor_graph_nodes')
    visitor_graph_edges_source_node: Mapped[list['VisitorGraphEdges']] = relationship('VisitorGraphEdges', foreign_keys='[VisitorGraphEdges.source_node_id]', back_populates='source_node')
    visitor_graph_edges_target_node: Mapped[list['VisitorGraphEdges']] = relationship('VisitorGraphEdges', foreign_keys='[VisitorGraphEdges.target_node_id]', back_populates='target_node')


class Comments(Base):
    __tablename__ = 'comments'
    __table_args__ = (
        ForeignKeyConstraint(['blog_id'], ['blog_posts.id'], name='comments_blog_id_fkey'),
        ForeignKeyConstraint(['parent_id'], ['comments.id'], name='comments_parent_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.id'], name='comments_user_id_fkey'),
        PrimaryKeyConstraint('id', name='comments_pkey'),
        Index('idx_comments_approved', 'blog_id', 'is_approved'),
        Index('idx_comments_blog', 'blog_id'),
        Index('idx_comments_parent', 'parent_id', postgresql_where='(parent_id IS NOT NULL)')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    blog_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    author_name: Mapped[Optional[str]] = mapped_column(Text)
    author_email: Mapped[Optional[str]] = mapped_column(Text)

    blog: Mapped['BlogPosts'] = relationship('BlogPosts', back_populates='comments')
    parent: Mapped[Optional['Comments']] = relationship('Comments', remote_side=[id], back_populates='parent_reverse')
    parent_reverse: Mapped[list['Comments']] = relationship('Comments', remote_side=[parent_id], back_populates='parent')
    user: Mapped[Optional['Users']] = relationship('Users', back_populates='comments')


class JerryNotes(Base):
    __tablename__ = 'jerry_notes'
    __table_args__ = (
        ForeignKeyConstraint(['source_message_id'], ['assistant_messages.id'], name='jerry_notes_source_message_id_fkey'),
        ForeignKeyConstraint(['visitor_session_id'], ['assistant_sessions.id'], name='jerry_notes_visitor_session_id_fkey'),
        PrimaryKeyConstraint('id', name='jerry_notes_pkey'),
        Index('idx_jerry_notes_created', 'created_at'),
        Index('idx_jerry_notes_session', 'visitor_session_id'),
        Index('idx_jerry_notes_starred', 'is_starred'),
        Index('idx_jerry_notes_type', 'note_type')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    visitor_session_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    visitor_id: Mapped[str] = mapped_column(Text, nullable=False)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    note_type: Mapped[NoteType] = mapped_column(Enum(NoteType, values_callable=lambda cls: [member.value for member in cls], name='note_type'), nullable=False, server_default=text("'general'::note_type"))
    is_starred: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    is_feedback: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text('false'))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    source_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    conversation_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    expires_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(True))

    source_message: Mapped[Optional['AssistantMessages']] = relationship('AssistantMessages', back_populates='jerry_notes')
    visitor_session: Mapped['AssistantSessions'] = relationship('AssistantSessions', back_populates='jerry_notes')


class ProjectBlocks(Base):
    __tablename__ = 'project_blocks'
    __table_args__ = (
        ForeignKeyConstraint(['project_id'], ['projects.id'], name='project_blocks_project_id_fkey'),
        PrimaryKeyConstraint('id', name='project_blocks_pkey'),
        Index('idx_project_blocks_position', 'project_id', 'position'),
        Index('idx_project_blocks_project', 'project_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    block_type: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text('0'))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    project: Mapped['Projects'] = relationship('Projects', back_populates='project_blocks')


class VisitorGraphEdges(Base):
    __tablename__ = 'visitor_graph_edges'
    __table_args__ = (
        ForeignKeyConstraint(['source_node_id'], ['visitor_graph_nodes.id'], name='visitor_graph_edges_source_node_id_fkey'),
        ForeignKeyConstraint(['target_node_id'], ['visitor_graph_nodes.id'], name='visitor_graph_edges_target_node_id_fkey'),
        PrimaryKeyConstraint('id', name='visitor_graph_edges_pkey'),
        Index('idx_vge_source', 'source_node_id'),
        Index('idx_vge_target', 'target_node_id')
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('gen_random_uuid()'))
    source_node_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_node_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(True), nullable=False, server_default=text('now()'))

    source_node: Mapped['VisitorGraphNodes'] = relationship('VisitorGraphNodes', foreign_keys=[source_node_id], back_populates='visitor_graph_edges_source_node')
    target_node: Mapped['VisitorGraphNodes'] = relationship('VisitorGraphNodes', foreign_keys=[target_node_id], back_populates='visitor_graph_edges_target_node')
