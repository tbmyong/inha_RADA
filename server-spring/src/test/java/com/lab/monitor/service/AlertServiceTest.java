package com.lab.monitor.service;

import com.lab.monitor.dto.AgentJudgmentDto;
import com.lab.monitor.dto.MlResponse;
import com.lab.monitor.entity.AiJudgmentHistory;
import com.lab.monitor.entity.AnomalyHistory;
import com.lab.monitor.repository.AiJudgmentRepository;
import com.lab.monitor.repository.AlertRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

class AlertServiceTest {

    private AlertRepository alertRepository;
    private AiJudgmentRepository aiJudgmentRepository;
    private AlertService service;

    @BeforeEach
    void setUp() {
        alertRepository = mock(AlertRepository.class);
        aiJudgmentRepository = mock(AiJudgmentRepository.class);
        service = new AlertService(alertRepository, aiJudgmentRepository);
    }

    @Test
    void normal_overall_severity_does_not_persist() {
        MlResponse resp = MlResponse.builder().overallSeverity("NORMAL").build();
        service.handle(resp, "pc-1");
        verify(alertRepository, never()).save(any());
        verify(aiJudgmentRepository, never()).save(any());
    }

    @Test
    void null_overall_severity_does_not_persist() {
        MlResponse resp = MlResponse.builder().build();
        service.handle(resp, "pc-1");
        verify(alertRepository, never()).save(any());
        verify(aiJudgmentRepository, never()).save(any());
    }

    /**
     * P0-1 (docs/fp_field_analysis_v0.6.md §7-P0-1): LOW/OBSERVE is weak
     * signal and must not persist. Field data showed 3,330/4,853 rows
     * (68.6%) were LOW/OBSERVE under normal usage — they flood the
     * anomaly_history table without operator value.
     */
    @Test
    void low_observe_does_not_persist() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("LOW")
                .verdict("OBSERVE")
                .build();
        service.handle(resp, "pc-1");
        verify(alertRepository, never()).save(any());
        verify(aiJudgmentRepository, never()).save(any());
    }

    @Test
    void low_observe_case_insensitive_does_not_persist() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("low")
                .verdict("observe")
                .build();
        service.handle(resp, "pc-1");
        verify(alertRepository, never()).save(any());
    }

    /**
     * Negative — non-LOW severity with OBSERVE verdict is *not* skipped
     * by P0-1. Those mismatches (e.g. MEDIUM/OBSERVE, HIGH/OBSERVE) are
     * the target of P0-2 in a separate PR.
     */
    @Test
    void medium_observe_still_persists_for_now() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("MEDIUM")
                .verdict("OBSERVE")
                .build();
        AnomalyHistory saved = AnomalyHistory.builder().id(99L).build();
        when(alertRepository.save(any(AnomalyHistory.class))).thenReturn(saved);
        service.handle(resp, "pc-1");
        verify(alertRepository).save(any());
    }

    /**
     * Negative — LOW with non-OBSERVE verdict (e.g. LOW/SUSPICIOUS, if
     * that ever surfaces) is *not* skipped by P0-1.
     */
    @Test
    void low_non_observe_still_persists() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("LOW")
                .verdict("SUSPICIOUS")
                .build();
        AnomalyHistory saved = AnomalyHistory.builder().id(99L).build();
        when(alertRepository.save(any(AnomalyHistory.class))).thenReturn(saved);
        service.handle(resp, "pc-1");
        verify(alertRepository).save(any());
    }

    @Test
    void high_overall_severity_persists_anomaly_and_5field_judgment() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .message("cpu saturated")
                .scores(Map.of("cpu", 0.99))
                .alerts(List.of(Map.of("cpu_overload", true)))
                .agent(AgentJudgmentDto.builder()
                        .judgment("ANOMALY")
                        .severity("HIGH")
                        .reason("cpu>95 for 60s")
                        .action("ESCALATE")
                        .hwDegradation("CONFIRMED")
                        .isMock(false)
                        .modelName("claude-sonnet-4")
                        .build())
                .build();
        AnomalyHistory savedAnomaly = AnomalyHistory.builder().id(42L).build();
        when(alertRepository.save(any(AnomalyHistory.class))).thenReturn(savedAnomaly);

        service.handle(resp, "pc-1");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getSeverity()).isEqualTo("HIGH");
        assertThat(a.getValue().getAnomalyType()).isEqualTo("DANGEROUS");
        assertThat(a.getValue().getMessage()).isEqualTo("cpu saturated");
        assertThat(a.getValue().getAlerts())
                .containsExactly(Map.of("cpu_overload", true));

        ArgumentCaptor<AiJudgmentHistory> j = ArgumentCaptor.forClass(AiJudgmentHistory.class);
        verify(aiJudgmentRepository).save(j.capture());
        AiJudgmentHistory v = j.getValue();
        assertThat(v.getAnomalyId()).isEqualTo(42L);
        // 5 direct columns
        assertThat(v.getJudgment()).isEqualTo("ANOMALY");
        assertThat(v.getSeverity()).isEqualTo("HIGH");
        assertThat(v.getReason()).isEqualTo("cpu>95 for 60s");
        assertThat(v.getAction()).isEqualTo("ESCALATE");
        assertThat(v.getIsMock()).isFalse();
        // legacy compatibility: verdict mirrors judgment
        assertThat(v.getVerdict()).isEqualTo("ANOMALY");
        // details preserves raw agent block (snake_case keys)
        assertThat(v.getDetails()).containsEntry("judgment", "ANOMALY");
        assertThat(v.getDetails()).containsEntry("reason", "cpu>95 for 60s");
        assertThat(v.getDetails()).containsEntry("hw_degradation", "CONFIRMED");
        assertThat(v.getDetails()).containsEntry("is_mock", false);
    }

    @Test
    void high_overall_severity_without_agent_block_still_persists() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(7L); return ah; });

        service.handle(resp, "pc-2");

        ArgumentCaptor<AiJudgmentHistory> j = ArgumentCaptor.forClass(AiJudgmentHistory.class);
        verify(aiJudgmentRepository).save(j.capture());
        assertThat(j.getValue().getJudgment()).isNull();
        assertThat(j.getValue().getVerdict()).isNull();
        assertThat(j.getValue().getDetails()).isNull();
    }

    @Test
    void isMock_heuristic_uses_explicit_flag_when_present() {
        AgentJudgmentDto agent = AgentJudgmentDto.builder()
                .isMock(true).modelName("claude-sonnet").build();
        assertThat(AlertService.resolveIsMock(agent)).isTrue();
    }

    @Test
    void isMock_heuristic_falls_back_to_modelName_mock_substring() {
        AgentJudgmentDto agent = AgentJudgmentDto.builder()
                .modelName("MockAgent-v2").build();
        assertThat(AlertService.resolveIsMock(agent)).isTrue();
    }

    @Test
    void isMock_heuristic_falls_back_to_modelName_stub_substring() {
        AgentJudgmentDto agent = AgentJudgmentDto.builder()
                .modelName("local-stub").build();
        assertThat(AlertService.resolveIsMock(agent)).isTrue();
    }

    @Test
    void isMock_heuristic_real_model_resolves_to_false() {
        AgentJudgmentDto agent = AgentJudgmentDto.builder()
                .modelName("claude-sonnet-4").build();
        assertThat(AlertService.resolveIsMock(agent)).isFalse();
    }

    @Test
    void isMock_heuristic_null_modelName_resolves_to_false() {
        AgentJudgmentDto agent = AgentJudgmentDto.builder().build();
        assertThat(AlertService.resolveIsMock(agent)).isFalse();
    }

    @Test
    void hwDegradation_NONE_roundtrips_into_details() {
        runHwDegradationRoundTrip("NONE");
    }

    @Test
    void hwDegradation_SUSPECTED_roundtrips_into_details() {
        runHwDegradationRoundTrip("SUSPECTED");
    }

    @Test
    void hwDegradation_CONFIRMED_roundtrips_into_details() {
        runHwDegradationRoundTrip("CONFIRMED");
    }

    private void runHwDegradationRoundTrip(String value) {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .agent(AgentJudgmentDto.builder()
                        .judgment("ANOMALY")
                        .severity("HIGH")
                        .hwDegradation(value)
                        .build())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(1L); return ah; });

        service.handle(resp, "pc-hw");

        ArgumentCaptor<AiJudgmentHistory> j = ArgumentCaptor.forClass(AiJudgmentHistory.class);
        verify(aiJudgmentRepository).save(j.capture());
        assertThat(j.getValue().getDetails()).containsEntry("hw_degradation", value);
    }

    /**
     * Originally validated that LOW/OBSERVE was persisted. P0-1 reverses
     * that policy (see {@link #low_observe_does_not_persist()}). To keep
     * coverage of the OBSERVE-verdict path that should still persist,
     * the fixture now uses severity=MEDIUM (which §3-B's HIGH/OBSERVE
     * mismatch will be the target of P0-2 in a separate PR, but
     * MEDIUM/OBSERVE persistence is still the current behaviour).
     */
    @Test
    void observe_verdict_with_medium_severity_is_persisted() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("MEDIUM")
                .verdict("OBSERVE")
                .message("baseline drift")
                .agent(AgentJudgmentDto.builder()
                        .judgment("OBSERVE")
                        .severity("LOW")
                        .hwDegradation("SUSPECTED")
                        .build())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(9L); return ah; });

        service.handle(resp, "pc-obs");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getSeverity()).isEqualTo("MEDIUM");
        assertThat(a.getValue().getAnomalyType()).isEqualTo("OBSERVE");

        ArgumentCaptor<AiJudgmentHistory> j = ArgumentCaptor.forClass(AiJudgmentHistory.class);
        verify(aiJudgmentRepository).save(j.capture());
        assertThat(j.getValue().getJudgment()).isEqualTo("OBSERVE");
        assertThat(j.getValue().getSeverity()).isEqualTo("LOW");
        assertThat(j.getValue().getDetails()).containsEntry("hw_degradation", "SUSPECTED");
    }

    @Test
    void score_breakdown_nested_keys_preserved_in_anomaly_scores() {
        Map<String, Object> breakdown = Map.of(
                "final", 0.42,
                "context_multiplier", 0.9);
        Map<String, Object> scores = Map.of(
                "cpu", 0.42,
                "score_breakdown", breakdown);

        MlResponse resp = MlResponse.builder()
                .overallSeverity("MEDIUM")
                .verdict("OBSERVE")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(3L); return ah; });

        service.handle(resp, "pc-sb");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("score_breakdown");
        Object nested = saved.get("score_breakdown");
        assertThat(nested).isInstanceOf(Map.class);
        assertThat((Map<String, Object>) nested).containsEntry("final", 0.42);
    }

    @Test
    @SuppressWarnings("unchecked")
    void score_breakdown_eight_keys_preserved_in_anomaly_scores() {
        Map<String, Object> breakdown = Map.of(
                "resource", 0.10,
                "network", 0.20,
                "process", 0.30,
                "episode", 0.40,
                "correlation", 0.50,
                "ml", 0.60,
                "context_discount", 0.70,
                "final", 0.80);
        Map<String, Object> scores = Map.of("score_breakdown", breakdown);

        MlResponse resp = MlResponse.builder()
                .overallSeverity("MEDIUM")
                .verdict("OBSERVE")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(11L); return ah; });

        service.handle(resp, "pc-sb8");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("score_breakdown");
        Map<String, Object> nested = (Map<String, Object>) saved.get("score_breakdown");
        assertThat(nested).containsEntry("resource", 0.10);
        assertThat(nested).containsEntry("network", 0.20);
        assertThat(nested).containsEntry("process", 0.30);
        assertThat(nested).containsEntry("episode", 0.40);
        assertThat(nested).containsEntry("correlation", 0.50);
        assertThat(nested).containsEntry("ml", 0.60);
        assertThat(nested).containsEntry("context_discount", 0.70);
        assertThat(nested).containsEntry("final", 0.80);
    }

    @Test
    @SuppressWarnings("unchecked")
    void retrieval_evidence_merged_into_scores_jsonb_when_present() {
        Map<String, Object> topK0 = Map.of(
                "segment_id", "seg-1",
                "pc_id", "pc-x",
                "distance", 0.42,
                "verdict", "HIGH_RISK");
        Map<String, Object> evidence = Map.of(
                "available", true,
                "retrieval_score", 3,
                "peer_mismatch", true,
                "novelty", false,
                "top_k", List.of(topK0));
        Map<String, Object> scores = Map.of(
                "cpu", 0.99,
                "score_breakdown", Map.of("retrieval", 3));

        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .retrievalEvidence(evidence)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(101L); return ah; });

        service.handle(resp, "pc-re");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("retrieval_evidence");
        assertThat(saved).containsKey("score_breakdown");
        Map<String, Object> savedEvidence = (Map<String, Object>) saved.get("retrieval_evidence");
        assertThat(savedEvidence).containsEntry("retrieval_score", 3);
        assertThat(savedEvidence).containsEntry("peer_mismatch", true);
        List<Map<String, Object>> savedTopK = (List<Map<String, Object>>) savedEvidence.get("top_k");
        assertThat(savedTopK).hasSize(1);
        assertThat(savedTopK.get(0)).containsEntry("segment_id", "seg-1");
        assertThat(savedTopK.get(0)).containsEntry("distance", 0.42);
    }

    @Test
    void retrieval_evidence_absent_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(102L); return ah; });

        service.handle(resp, "pc-re-none");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).doesNotContainKey("retrieval_evidence");
        assertThat(saved).containsEntry("cpu", 0.5);
    }

    @Test
    void retrieval_evidence_empty_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .retrievalEvidence(Map.of())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(103L); return ah; });

        service.handle(resp, "pc-re-empty");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("retrieval_evidence");
    }

    @Test
    @SuppressWarnings("unchecked")
    void signals_missing_merged_into_scores_jsonb_when_present() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .signalsMissing(List.of("network", "process"))
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(201L); return ah; });

        service.handle(resp, "pc-sm");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("signals_missing");
        List<String> sm = (List<String>) saved.get("signals_missing");
        assertThat(sm).containsExactly("network", "process");
        // 원 scores 키도 보존
        assertThat(saved).containsEntry("cpu", 0.5);
    }

    @Test
    void signals_missing_empty_or_null_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .signalsMissing(List.of())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(202L); return ah; });

        service.handle(resp, "pc-sm-empty");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("signals_missing");
    }

    @Test
    @SuppressWarnings("unchecked")
    void category_signals_merged_into_scores_jsonb_when_present() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        Map<String, Object> categorySignals = Map.of(
                "resource_abnormal", true,
                "network_abnormal", false,
                "system_abnormal", false,
                "sustained_minutes", 7,
                "triggered_patterns", List.of("cpu_sustained_high"),
                "verdict_from_gating", "DANGEROUS");
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .categorySignals(categorySignals)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(301L); return ah; });

        service.handle(resp, "pc-cs");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("category_signals");
        Map<String, Object> savedCs = (Map<String, Object>) saved.get("category_signals");
        assertThat(savedCs).containsEntry("resource_abnormal", true);
        assertThat(savedCs).containsEntry("sustained_minutes", 7);
        assertThat(savedCs).containsEntry("verdict_from_gating", "DANGEROUS");
        List<String> patterns = (List<String>) savedCs.get("triggered_patterns");
        assertThat(patterns).containsExactly("cpu_sustained_high");
        // original scores key preserved
        assertThat(saved).containsEntry("cpu", 0.5);
    }

    @Test
    void category_signals_absent_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(302L); return ah; });

        service.handle(resp, "pc-cs-none");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("category_signals");
        assertThat(a.getValue().getScores()).containsEntry("cpu", 0.5);
    }

    @Test
    void category_signals_empty_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .categorySignals(Map.of())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(303L); return ah; });

        service.handle(resp, "pc-cs-empty");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("category_signals");
    }

    @Test
    @SuppressWarnings("unchecked")
    void retrieval_evidence_signals_missing_category_signals_all_three_preserved_together() {
        Map<String, Object> scores = Map.of("cpu", 0.9);
        Map<String, Object> evidence = Map.of("retrieval_score", 2, "peer_mismatch", false);
        Map<String, Object> categorySignals = Map.of(
                "resource_abnormal", true,
                "verdict_from_gating", "OBSERVE");

        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .retrievalEvidence(evidence)
                .signalsMissing(List.of("network"))
                .categorySignals(categorySignals)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(304L); return ah; });

        service.handle(resp, "pc-triple");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("retrieval_evidence");
        assertThat(saved).containsKey("signals_missing");
        assertThat(saved).containsKey("category_signals");
        assertThat(saved).containsEntry("cpu", 0.9);
        assertThat((Map<String, Object>) saved.get("retrieval_evidence"))
                .containsEntry("retrieval_score", 2);
        assertThat((List<String>) saved.get("signals_missing")).containsExactly("network");
        assertThat((Map<String, Object>) saved.get("category_signals"))
                .containsEntry("verdict_from_gating", "OBSERVE");
    }

    /**
     * P0-3 (docs/fp_field_analysis_v0.6.md §7-P0-3): evidence_meta block
     * (promotion gating audit) must be preserved verbatim under
     * scores.evidence_meta so Grafana can query gating outcomes by
     * pure SQL.
     */
    @Test
    @SuppressWarnings("unchecked")
    void evidence_meta_merged_into_scores_jsonb_when_present() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        Map<String, Object> evidenceMeta = Map.of(
                "active_signal_count", 5,
                "category_count", 3,
                "active_categories", List.of("resource", "network", "ml"),
                "active_signals", List.of("cpu_flat", "net_out_sustained", "gpu_high", "mem_high", "ml_anomaly"),
                "promotion_gated", false,
                "promotion_reason", "gating_passed",
                "fast_path_match", "mining_known");
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .evidenceMeta(evidenceMeta)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(401L); return ah; });

        service.handle(resp, "pc-em");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("evidence_meta");
        Map<String, Object> savedMeta = (Map<String, Object>) saved.get("evidence_meta");
        assertThat(savedMeta).containsEntry("active_signal_count", 5);
        assertThat(savedMeta).containsEntry("category_count", 3);
        assertThat(savedMeta).containsEntry("promotion_gated", false);
        assertThat(savedMeta).containsEntry("promotion_reason", "gating_passed");
        assertThat(savedMeta).containsEntry("fast_path_match", "mining_known");
        List<String> cats = (List<String>) savedMeta.get("active_categories");
        assertThat(cats).containsExactly("resource", "network", "ml");
        // original scores key preserved
        assertThat(saved).containsEntry("cpu", 0.5);
    }

    @Test
    void evidence_meta_absent_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(402L); return ah; });

        service.handle(resp, "pc-em-none");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("evidence_meta");
        assertThat(a.getValue().getScores()).containsEntry("cpu", 0.5);
    }

    @Test
    void evidence_meta_empty_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .evidenceMeta(Map.of())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(403L); return ah; });

        service.handle(resp, "pc-em-empty");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("evidence_meta");
    }

    /**
     * P1-1 (docs/fp_field_analysis_v0.6.md §7-P1-1): local_evidence
     * (LOCAL_* agent advisories that no longer pollute alerts[]) is
     * preserved verbatim under scores.local_evidence for audit.
     */
    @Test
    @SuppressWarnings("unchecked")
    void local_evidence_merged_into_scores_jsonb_when_present() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        List<Map<String, Object>> local = List.of(
                Map.of("type", "LOCAL_MEM_HIGH", "severity", "HIGH",
                       "detail", "[에이전트] mem 95", "score", 0),
                Map.of("type", "LOCAL_HW_CPU_DEGRADATION", "severity", "MEDIUM",
                       "detail", "[에이전트] cpu drift", "score", 0));
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .localEvidence(local)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(501L); return ah; });

        service.handle(resp, "pc-le");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKey("local_evidence");
        List<Map<String, Object>> savedLocal =
                (List<Map<String, Object>>) saved.get("local_evidence");
        assertThat(savedLocal).hasSize(2);
        assertThat(savedLocal.get(0)).containsEntry("type", "LOCAL_MEM_HIGH");
        assertThat(savedLocal.get(1)).containsEntry("severity", "MEDIUM");
        assertThat(saved).containsEntry("cpu", 0.5);
    }

    @Test
    void local_evidence_absent_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(502L); return ah; });

        service.handle(resp, "pc-le-none");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("local_evidence");
    }

    @Test
    void local_evidence_empty_leaves_scores_untouched() {
        Map<String, Object> scores = Map.of("cpu", 0.5);
        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .localEvidence(List.of())
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(503L); return ah; });

        service.handle(resp, "pc-le-empty");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        assertThat(a.getValue().getScores()).doesNotContainKey("local_evidence");
    }

    // ──────────────────────────────────────────
    // P1-3 alert cooldown (docs/fp_field_analysis_v0.6.md §7-P1-3)
    // ──────────────────────────────────────────

    @Test
    void cooldown_drops_duplicate_within_window() {
        // 60s cooldown — second persist of same (pc,verdict) within window is skipped.
        AlertService svc = new AlertService(alertRepository, aiJudgmentRepository, 60L);
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(601L); return ah; });

        MlResponse r1 = MlResponse.builder()
                .overallSeverity("HIGH").verdict("DANGEROUS").build();
        svc.handle(r1, "pc-cd1");
        svc.handle(r1, "pc-cd1");  // dedupe
        svc.handle(r1, "pc-cd1");  // dedupe

        verify(alertRepository, times(1)).save(any(AnomalyHistory.class));
    }

    @Test
    void cooldown_does_not_dedupe_across_pcs() {
        AlertService svc = new AlertService(alertRepository, aiJudgmentRepository, 60L);
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(602L); return ah; });

        MlResponse r = MlResponse.builder()
                .overallSeverity("HIGH").verdict("DANGEROUS").build();
        svc.handle(r, "pc-A");
        svc.handle(r, "pc-B");
        svc.handle(r, "pc-C");

        verify(alertRepository, times(3)).save(any(AnomalyHistory.class));
    }

    @Test
    void cooldown_does_not_dedupe_different_verdicts_for_same_pc() {
        AlertService svc = new AlertService(alertRepository, aiJudgmentRepository, 60L);
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(603L); return ah; });

        MlResponse r1 = MlResponse.builder()
                .overallSeverity("HIGH").verdict("HIGH_RISK").build();
        MlResponse r2 = MlResponse.builder()
                .overallSeverity("MEDIUM").verdict("SUSPICIOUS").build();
        svc.handle(r1, "pc-V");
        svc.handle(r2, "pc-V");

        verify(alertRepository, times(2)).save(any(AnomalyHistory.class));
    }

    @Test
    void cooldown_zero_disables_dedupe() {
        // cooldownSeconds=0 → every persist goes through.
        AlertService svc = new AlertService(alertRepository, aiJudgmentRepository, 0L);
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(604L); return ah; });

        MlResponse r = MlResponse.builder()
                .overallSeverity("HIGH").verdict("HIGH_RISK").build();
        svc.handle(r, "pc-Z");
        svc.handle(r, "pc-Z");
        svc.handle(r, "pc-Z");

        verify(alertRepository, times(3)).save(any(AnomalyHistory.class));
    }

    @Test
    @SuppressWarnings("unchecked")
    void evidence_meta_coexists_with_retrieval_and_category_blocks() {
        Map<String, Object> scores = Map.of("cpu", 0.9);
        Map<String, Object> evidence = Map.of("retrieval_score", 2);
        Map<String, Object> categorySignals = Map.of("verdict_from_gating", "OBSERVE");
        Map<String, Object> evidenceMeta = new java.util.LinkedHashMap<>();
        evidenceMeta.put("promotion_gated", true);
        evidenceMeta.put("promotion_reason", "gating_blocked:medium(sig=2<3)");
        evidenceMeta.put("fast_path_match", null);
        evidenceMeta.put("active_signal_count", 2);
        evidenceMeta.put("category_count", 1);

        MlResponse resp = MlResponse.builder()
                .overallSeverity("HIGH")
                .verdict("DANGEROUS")
                .scores(scores)
                .retrievalEvidence(evidence)
                .signalsMissing(List.of("network"))
                .categorySignals(categorySignals)
                .evidenceMeta(evidenceMeta)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(404L); return ah; });

        service.handle(resp, "pc-quad");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        assertThat(saved).containsKeys(
                "retrieval_evidence", "signals_missing",
                "category_signals", "evidence_meta");
        assertThat((Map<String, Object>) saved.get("evidence_meta"))
                .containsEntry("promotion_gated", true);
    }

    @Test
    @SuppressWarnings("unchecked")
    void score_breakdown_final_can_be_negative_after_context_discount() {
        Map<String, Object> breakdown = Map.of(
                "resource", 0.10,
                "network", 0.05,
                "process", 0.05,
                "episode", 0.10,
                "correlation", 0.10,
                "ml", 0.08,
                "context_discount", 0.6,
                "final", -0.12);
        Map<String, Object> scores = Map.of("score_breakdown", breakdown);

        MlResponse resp = MlResponse.builder()
                .overallSeverity("MEDIUM")
                .verdict("OBSERVE")
                .scores(scores)
                .build();
        when(alertRepository.save(any(AnomalyHistory.class)))
                .thenAnswer(inv -> { AnomalyHistory ah = inv.getArgument(0); ah.setId(12L); return ah; });

        service.handle(resp, "pc-sb-neg");

        ArgumentCaptor<AnomalyHistory> a = ArgumentCaptor.forClass(AnomalyHistory.class);
        verify(alertRepository).save(a.capture());
        Map<String, Object> saved = a.getValue().getScores();
        Map<String, Object> nested = (Map<String, Object>) saved.get("score_breakdown");
        assertThat(nested).containsEntry("context_discount", 0.6);
        assertThat(nested).containsEntry("final", -0.12);
    }
}
