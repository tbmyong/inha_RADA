package com.lab.monitor.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lab.monitor.dto.AgentJudgmentDto;
import com.lab.monitor.dto.MlResponse;
import com.lab.monitor.entity.AiJudgmentHistory;
import com.lab.monitor.entity.AnomalyHistory;
import com.lab.monitor.repository.AiJudgmentRepository;
import com.lab.monitor.repository.AlertRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
public class AlertService {

    private final AlertRepository alertRepository;
    private final AiJudgmentRepository aiJudgmentRepository;
    private final ObjectMapper objectMapper;

    public AlertService(AlertRepository alertRepository,
                        AiJudgmentRepository aiJudgmentRepository) {
        this.alertRepository = alertRepository;
        this.aiJudgmentRepository = aiJudgmentRepository;
        this.objectMapper = new ObjectMapper();
    }

    @Transactional
    public void handle(MlResponse resp, String pcId) {
        if (resp == null
                || resp.getOverallSeverity() == null
                || "NORMAL".equalsIgnoreCase(resp.getOverallSeverity())) {
            return;
        }
        // P0-1 (docs/fp_field_analysis_v0.6.md §7-P0-1): do not persist
        // verdict=OBSERVE & severity=LOW. Those are weak signals that
        // flooded anomaly_history (3,330/4,853 rows in field data, 68.6%)
        // without operator value. Stage 1 — Spring-side filter only, ML
        // response unchanged. Stage 2 (later PR) — ML emits an explicit
        // should_persist=false hint.
        if ("LOW".equalsIgnoreCase(resp.getOverallSeverity())
                && "OBSERVE".equalsIgnoreCase(resp.getVerdict())) {
            log.debug("P0-1 skip: LOW/OBSERVE not persisted pcId={}", pcId);
            return;
        }
        OffsetDateTime now = OffsetDateTime.now();

        AnomalyHistory anomaly = AnomalyHistory.builder()
                .pcId(pcId)
                .detectedAt(now)
                .severity(resp.getOverallSeverity())
                .anomalyType(resp.getVerdict())
                .message(resp.getMessage())
                .scores(mergeAuditExtras(resp.getScores(),
                        resp.getRetrievalEvidence(),
                        resp.getSignalsMissing(),
                        resp.getCategorySignals()))
                .alerts(resp.getAlerts())
                .build();
        AnomalyHistory saved = alertRepository.save(anomaly);

        AgentJudgmentDto agent = resp.getAgent();

        AiJudgmentHistory.AiJudgmentHistoryBuilder b = AiJudgmentHistory.builder()
                .pcId(pcId)
                .judgedAt(now)
                .anomalyId(saved.getId());

        if (agent != null) {
            b.judgment(agent.getJudgment())
             .severity(agent.getSeverity())
             .reason(agent.getReason())
             .action(agent.getAction())
             .isMock(resolveIsMock(agent))
             .modelName(agent.getModelName())
             // legacy compatibility: verdict mirrors judgment
             .verdict(agent.getJudgment())
             .details(toRawMap(agent));
        }

        aiJudgmentRepository.save(b.build());

        log.info("Anomaly recorded pcId={} overallSeverity={} verdict={} id={}",
                pcId, resp.getOverallSeverity(), resp.getVerdict(), saved.getId());
    }

    /**
     * Resolve is_mock with a model_name heuristic fallback.
     * If the agent explicitly sets is_mock, use it. Otherwise infer:
     * model_name containing "mock" or "stub" (case-insensitive) → true,
     * otherwise false. A null/blank model_name with null is_mock → false.
     */
    static Boolean resolveIsMock(AgentJudgmentDto agent) {
        if (agent.getIsMock() != null) return agent.getIsMock();
        String name = agent.getModelName();
        if (name == null) return false;
        String lower = name.toLowerCase();
        return lower.contains("mock") || lower.contains("stub");
    }

    /**
     * Merge retrieval evidence into the scores JSONB under key {@code retrieval_evidence}.
     * Returns a mutable copy when evidence is present so the caller-supplied scores map
     * (which may be immutable, e.g. Map.of(...)) is not mutated. Returns the original
     * scores reference when evidence is null/empty for legacy/no-op compatibility.
     */
    static Map<String, Object> mergeRetrievalEvidence(Map<String, Object> scores,
                                                      Map<String, Object> retrievalEvidence) {
        if (retrievalEvidence == null || retrievalEvidence.isEmpty()) {
            return scores;
        }
        Map<String, Object> merged = new LinkedHashMap<>();
        if (scores != null) {
            merged.putAll(scores);
        }
        merged.put("retrieval_evidence", retrievalEvidence);
        return merged;
    }

    /**
     * F5: merge both retrieval_evidence and signals_missing into the scores JSONB.
     * Always returns a mutable copy when either extra is present so the caller-
     * supplied scores map (potentially {@code Map.of(...)}) is not mutated.
     * Returns the original scores reference when both extras are null/empty.
     */
    static Map<String, Object> mergeAuditExtras(Map<String, Object> scores,
                                                Map<String, Object> retrievalEvidence,
                                                List<String> signalsMissing) {
        return mergeAuditExtras(scores, retrievalEvidence, signalsMissing, null);
    }

    /**
     * Merge retrieval_evidence + signals_missing + category_signals into the scores
     * JSONB. Always returns a mutable copy when any extra is present so the caller-
     * supplied scores map (potentially {@code Map.of(...)}) is not mutated. Returns
     * the original scores reference when all extras are null/empty.
     */
    static Map<String, Object> mergeAuditExtras(Map<String, Object> scores,
                                                Map<String, Object> retrievalEvidence,
                                                List<String> signalsMissing,
                                                Map<String, Object> categorySignals) {
        boolean hasEvidence = retrievalEvidence != null && !retrievalEvidence.isEmpty();
        boolean hasMissing = signalsMissing != null && !signalsMissing.isEmpty();
        boolean hasCategory = categorySignals != null && !categorySignals.isEmpty();
        if (!hasEvidence && !hasMissing && !hasCategory) {
            return scores;
        }
        Map<String, Object> merged = new LinkedHashMap<>();
        if (scores != null) {
            merged.putAll(scores);
        }
        if (hasEvidence) {
            merged.put("retrieval_evidence", retrievalEvidence);
        }
        if (hasMissing) {
            merged.put("signals_missing", signalsMissing);
        }
        if (hasCategory) {
            merged.put("category_signals", categorySignals);
        }
        return merged;
    }

    /** Preserve the agent block verbatim as JSON map (snake_case keys). */
    @SuppressWarnings("unchecked")
    private Map<String, Object> toRawMap(AgentJudgmentDto agent) {
        try {
            return objectMapper.convertValue(agent, Map.class);
        } catch (IllegalArgumentException e) {
            return null;
        }
    }
}
