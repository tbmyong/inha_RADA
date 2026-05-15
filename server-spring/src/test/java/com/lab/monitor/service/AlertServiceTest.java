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

    @Test
    void observe_verdict_with_low_severity_is_persisted() {
        MlResponse resp = MlResponse.builder()
                .overallSeverity("LOW")
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
        assertThat(a.getValue().getSeverity()).isEqualTo("LOW");
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
                .overallSeverity("LOW")
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
                .overallSeverity("LOW")
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
                .overallSeverity("LOW")
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
