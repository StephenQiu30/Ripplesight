from ai.capability_models import AiCapabilityConfiguration
from ai.models import AiCall
from analysis.editorial_models import (
    EditorialContentState,
    EditorialOverride,
    EditorialRun,
    EditorialSource,
    EditorialSourceVersion,
    EditorialStage,
)
from analysis.evaluation_models import SelectBenchResult, SelectBenchRun
from analysis.models import (
    AnalysisPromptActivation,
    AnalysisPromptRuntimeSession,
    ContentAnnotation,
)
from analysis.translation_models import ContentTranslationBatch, ContentTranslationRun
from connections.editorial_icon_models import EditorialSourceIcon
from connections.editorial_models import (
    EditorialSourceMaterialReceipt,
    EditorialSourceProfile,
    EditorialSourceRun,
)
from connections.editorial_models import (
    EditorialSourceVersion as EditorialSourceProfileVersion,
)
from connections.models import (
    SourceCapabilityEvidence,
    SourceConnection,
    SourceConnectionVersion,
)
from content.editorial_rendered_models import ContentRenderedMaterial
from content.models import (
    ContentDiscovery,
    ContentObservation,
    ContentRecord,
    ContentThread,
    ContentVersion,
    ContentVersionRelation,
    ContentVisibilityObservation,
    HotlistEntryRecord,
    HotlistSnapshot,
)
from db.base import Base
from events.embedding_models import EventContentEmbedding
from events.fact_models import (
    EventDerivedContent,
    EventFact,
    EventFactAssignment,
    EventFactMember,
    EventGroupingAssessment,
    EventGroupingOverride,
    EventRevisionOperation,
)
from events.heat_models import EventAttentionSignal, EventAttentionSnapshot, EventAttentionSource
from events.models import Event, EventCandidate, EventMember
from events.story_models import EventStoryLink
from evidence.models import (
    CleanupTarget,
    DeletionDirective,
    EvidenceResource,
    ProvenanceManifest,
    ProvenanceManifestItem,
    RetentionPolicy,
    SourceAccessPolicy,
)
from jobs.models import (
    CollectionDueWindow,
    CoverageWindow,
    Job,
    JobAttempt,
    JobStageAttempt,
    OutboxMessage,
    ProcessedMessage,
    ResourceBudgetPolicy,
    ResourceBudgetReservation,
    ResourceBudgetWindow,
    ResourceComponentPolicy,
    ResourceUsageAttempt,
)
from knowledge.models import KnowledgeExport
from leaderboard.models import (
    LeaderboardAlias,
    LeaderboardFxRate,
    LeaderboardModel,
    LeaderboardPrice,
    LeaderboardRanking,
    LeaderboardRun,
    LeaderboardScore,
    LeaderboardSnapshot,
    LeaderboardSourceState,
)
from monitors.codex_models import (
    CodexResetEvent,
    CodexResetEventPost,
    CodexResetMonitor,
    CodexResetMonitorVersion,
    CodexResetPost,
    CodexResetRecognition,
    CodexResetReview,
    CodexResetScanGap,
)
from monitors.models import (
    FollowedAccount,
    FollowedAccountAlias,
    MonitorSchedule,
    MonitorTopic,
    MonitorTopicStatusEvent,
    MonitorTopicVersion,
)
from notifications.models import NotificationDelivery, NotificationTarget
from operations.models import (
    DictionaryVersion,
    Feedback,
    FeedbackAttachment,
    FeedbackCooldown,
    OperatorAuditOperation,
    ProcessHeartbeat,
)
from operations.site_models import SiteConfiguration
from publication.media_mirror_models import PublicationMediaFile, PublicationMediaRun
from publication.publication_models import (
    PublicationPolicyVersion,
    PublicationRecord,
    PublicationRepublishRun,
    PublicationRevision,
    PublicationSelectedChange,
    PublicationSourcePolicy,
    PublicationSyncState,
)
from reports.edition_models import ReportEdition, ReportEditionSchedule
from reports.models import Report

# Import each domain's models here for runtime mapping and clean-database verification.
# DDL ownership remains exclusively in database/schema.sql.
metadata = Base.metadata

__all__ = [
    "AiCall",
    "AiCapabilityConfiguration",
    "AnalysisPromptActivation",
    "AnalysisPromptRuntimeSession",
    "CleanupTarget",
    "CodexResetEvent",
    "CodexResetEventPost",
    "CodexResetMonitor",
    "CodexResetMonitorVersion",
    "CodexResetPost",
    "CodexResetRecognition",
    "CodexResetReview",
    "CodexResetScanGap",
    "CollectionDueWindow",
    "ContentAnnotation",
    "ContentDiscovery",
    "ContentObservation",
    "ContentRecord",
    "ContentRenderedMaterial",
    "ContentThread",
    "ContentTranslationBatch",
    "ContentTranslationRun",
    "ContentVersion",
    "ContentVersionRelation",
    "ContentVisibilityObservation",
    "CoverageWindow",
    "DeletionDirective",
    "DictionaryVersion",
    "EditorialContentState",
    "EditorialOverride",
    "EditorialRun",
    "EditorialSource",
    "EditorialSourceIcon",
    "EditorialSourceMaterialReceipt",
    "EditorialSourceProfile",
    "EditorialSourceProfileVersion",
    "EditorialSourceRun",
    "EditorialSourceVersion",
    "EditorialStage",
    "Event",
    "EventAttentionSignal",
    "EventAttentionSnapshot",
    "EventAttentionSource",
    "EventCandidate",
    "EventContentEmbedding",
    "EventDerivedContent",
    "EventFact",
    "EventFactAssignment",
    "EventFactMember",
    "EventGroupingAssessment",
    "EventGroupingOverride",
    "EventMember",
    "EventRevisionOperation",
    "EventStoryLink",
    "EvidenceResource",
    "Feedback",
    "FeedbackAttachment",
    "FeedbackCooldown",
    "FollowedAccount",
    "FollowedAccountAlias",
    "HotlistEntryRecord",
    "HotlistSnapshot",
    "Job",
    "JobAttempt",
    "JobStageAttempt",
    "KnowledgeExport",
    "LeaderboardAlias",
    "LeaderboardFxRate",
    "LeaderboardModel",
    "LeaderboardPrice",
    "LeaderboardRanking",
    "LeaderboardRun",
    "LeaderboardScore",
    "LeaderboardSnapshot",
    "LeaderboardSourceState",
    "MonitorSchedule",
    "MonitorTopic",
    "MonitorTopicStatusEvent",
    "MonitorTopicVersion",
    "NotificationDelivery",
    "NotificationTarget",
    "OperatorAuditOperation",
    "OutboxMessage",
    "ProcessHeartbeat",
    "ProcessedMessage",
    "ProvenanceManifest",
    "ProvenanceManifestItem",
    "PublicationMediaFile",
    "PublicationMediaRun",
    "PublicationPolicyVersion",
    "PublicationRecord",
    "PublicationRepublishRun",
    "PublicationRevision",
    "PublicationSelectedChange",
    "PublicationSourcePolicy",
    "PublicationSyncState",
    "Report",
    "ReportEdition",
    "ReportEditionSchedule",
    "ResourceBudgetPolicy",
    "ResourceBudgetReservation",
    "ResourceBudgetWindow",
    "ResourceComponentPolicy",
    "ResourceUsageAttempt",
    "RetentionPolicy",
    "SelectBenchResult",
    "SelectBenchRun",
    "SiteConfiguration",
    "SourceAccessPolicy",
    "SourceCapabilityEvidence",
    "SourceConnection",
    "SourceConnectionVersion",
    "metadata",
]
