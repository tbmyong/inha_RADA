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
        OffsetDateTime now = OffsetDateTime.now();

        AnomalyHistory anomaly = AnomalyHistory.builder()
                .pcId(pcId)
                .detectedAt(now)
                .severity(resp.getOverallSeverity())
                .anomalyType(resp.getVerdict())
                .message(resp.getMessage())
                .scores(resp.getScores())
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
