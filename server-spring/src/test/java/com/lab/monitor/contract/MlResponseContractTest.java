package com.lab.monitor.contract;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.lab.monitor.dto.MlResponse;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.InputStream;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Contract test for the ML server -> Server analysis response.
 *
 * After DTO realignment, the real ML payload should deserialize exhaustively into
 * MlResponse:
 *   - top-level: overall_severity, verdict, message, scores, alerts
 *   - nested:    agent.{judgment, severity, reason, action, hw_degradation}
 */
class MlResponseContractTest {

    private final ObjectMapper mapper = new ObjectMapper();

    private byte[] read(String path) throws IOException {
        try (InputStream is = getClass().getResourceAsStream(path)) {
            assertThat(is).as("fixture present: " + path).isNotNull();
            return is.readAllBytes();
        }
    }

    @Test
    void deserialize_high_risk_maps_all_seven_contract_fields() throws IOException {
        byte[] bytes = read("/fixtures/ml/analyze_high_risk.json");

        MlResponse mapped = mapper.readValue(bytes, MlResponse.class);

        assertThat(mapped.getOverallSeverity()).isEqualTo("HIGH");
        assertThat(mapped.getVerdict()).isEqualTo("DANGEROUS");
        assertThat(mapped.getMessage()).isNotBlank();
        assertThat(mapped.getScores()).containsKeys("cpu", "memory", "disk");
        // alerts is List<Map> after the realignment; high_risk fixture
        // ships one entry per detected anomaly type.
        assertThat(mapped.getAlerts()).hasSize(2);
        assertThat(mapped.getAlerts().get(0)).containsEntry("type", "cpu_overload");

        assertThat(mapped.getAgent()).isNotNull();
        assertThat(mapped.getAgent().getJudgment()).isEqualTo("ANOMALY");
        assertThat(mapped.getAgent().getSeverity()).isEqualTo("HIGH");
        assertThat(mapped.getAgent().getReason()).isNotBlank();
        assertThat(mapped.getAgent().getAction()).isEqualTo("ESCALATE");
        assertThat(mapped.getAgent().getHwDegradation()).isEqualTo("CONFIRMED");

        assertThat(mapped.getPolicyVersion()).isEqualTo("scoring-v0.4.0");
    }

    @Test
    void deserialize_normal_maps_all_seven_contract_fields() throws IOException {
        byte[] bytes = read("/fixtures/ml/analyze_normal.json");

        MlResponse mapped = mapper.readValue(bytes, MlResponse.class);

        assertThat(mapped.getOverallSeverity()).isEqualTo("NORMAL");
        assertThat(mapped.getVerdict()).isEqualTo("SAFE");
        assertThat(mapped.getScores()).containsKeys("cpu", "memory", "disk");
        assertThat(mapped.getAlerts()).isNotNull().isEmpty();

        assertThat(mapped.getAgent()).isNotNull();
        assertThat(mapped.getAgent().getJudgment()).isEqualTo("NORMAL");
        assertThat(mapped.getAgent().getSeverity()).isEqualTo("LOW");
        assertThat(mapped.getAgent().getReason()).isNotBlank();
        assertThat(mapped.getAgent().getAction()).isEqualTo("NONE");
        assertThat(mapped.getAgent().getHwDegradation()).isEqualTo("NONE");

        assertThat(mapped.getPolicyVersion()).isEqualTo("scoring-v0.4.0");
    }

    @Test
    void policy_version_absent_is_null() throws IOException {
        // Compatibility: before Team B ships the scoring v0.4.0 emitter,
        // ML payloads omit policy_version. Deserialization must still succeed
        // and the field must map to null.
        String json = "{\"overall_severity\":\"NORMAL\",\"verdict\":\"SAFE\"," +
                "\"scores\":{\"cpu\":0.0,\"memory\":0.0,\"disk\":0.0}," +
                "\"alerts\":[]," +
                "\"agent\":{\"judgment\":\"NORMAL\",\"severity\":\"LOW\"," +
                "\"reason\":\"x\",\"action\":\"NONE\",\"hw_degradation\":\"NONE\"}}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getPolicyVersion()).isNull();
        assertThat(mapped.getOverallSeverity()).isEqualTo("NORMAL");
    }

    @Test
    @SuppressWarnings("unchecked")
    void retrieval_evidence_block_deserializes_into_map() throws IOException {
        String json = "{\"overall_severity\":\"HIGH\",\"verdict\":\"DANGEROUS\"," +
                "\"retrieval_evidence\":{" +
                "\"available\":true," +
                "\"retrieval_score\":3," +
                "\"peer_mismatch\":true," +
                "\"novelty\":false," +
                "\"similar_high_risk_count\":2," +
                "\"top_k\":[" +
                "  {\"segment_id\":\"seg-1\",\"pc_id\":\"pc-x\",\"distance\":0.42," +
                "\"verdict\":\"HIGH_RISK\",\"timestamp\":\"2026-05-18T00:00:00Z\"}," +
                "  {\"segment_id\":\"seg-2\",\"pc_id\":\"pc-y\",\"distance\":12.0," +
                "\"verdict\":\"OBSERVE\"}" +
                "]}}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getRetrievalEvidence()).isNotNull();
        assertThat(mapped.getRetrievalEvidence()).containsEntry("retrieval_score", 3);
        assertThat(mapped.getRetrievalEvidence()).containsEntry("peer_mismatch", true);
        java.util.List<java.util.Map<String, Object>> topK =
                (java.util.List<java.util.Map<String, Object>>) mapped.getRetrievalEvidence().get("top_k");
        assertThat(topK).hasSize(2);
        assertThat(topK.get(0)).containsEntry("segment_id", "seg-1");
        assertThat(topK.get(0)).containsEntry("verdict", "HIGH_RISK");
    }

    @Test
    void retrieval_evidence_absent_is_null() throws IOException {
        String json = "{\"overall_severity\":\"NORMAL\",\"verdict\":\"SAFE\"}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getRetrievalEvidence()).isNull();
    }

    @Test
    void signals_missing_deserializes_into_list_of_strings() throws IOException {
        String json = "{\"overall_severity\":\"HIGH\",\"verdict\":\"DANGEROUS\"," +
                "\"signals_missing\":[\"network\",\"process\"]}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getSignalsMissing()).containsExactly("network", "process");
    }

    @Test
    void signals_missing_absent_is_null() throws IOException {
        String json = "{\"overall_severity\":\"NORMAL\",\"verdict\":\"SAFE\"}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getSignalsMissing()).isNull();
    }

    @Test
    @SuppressWarnings("unchecked")
    void category_signals_block_deserializes_into_map() throws IOException {
        String json = "{\"overall_severity\":\"HIGH\",\"verdict\":\"DANGEROUS\"," +
                "\"category_signals\":{" +
                "\"resource_abnormal\":true," +
                "\"network_abnormal\":false," +
                "\"system_abnormal\":false," +
                "\"sustained_minutes\":7," +
                "\"triggered_patterns\":[\"cpu_sustained_high\",\"mem_leak\"]," +
                "\"verdict_from_gating\":\"DANGEROUS\"" +
                "}}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getCategorySignals()).isNotNull();
        assertThat(mapped.getCategorySignals()).containsEntry("resource_abnormal", true);
        assertThat(mapped.getCategorySignals()).containsEntry("network_abnormal", false);
        assertThat(mapped.getCategorySignals()).containsEntry("sustained_minutes", 7);
        assertThat(mapped.getCategorySignals()).containsEntry("verdict_from_gating", "DANGEROUS");
        java.util.List<String> patterns =
                (java.util.List<String>) mapped.getCategorySignals().get("triggered_patterns");
        assertThat(patterns).containsExactly("cpu_sustained_high", "mem_leak");
    }

    @Test
    void category_signals_absent_is_null() throws IOException {
        String json = "{\"overall_severity\":\"NORMAL\",\"verdict\":\"SAFE\"}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getCategorySignals()).isNull();
    }

    @Test
    void unknown_keys_are_ignored() throws IOException {
        String json = "{\"overall_severity\":\"NORMAL\",\"verdict\":\"SAFE\"," +
                "\"future_field\":\"ignored\"," +
                "\"agent\":{\"judgment\":\"NORMAL\",\"severity\":\"LOW\"," +
                "\"reason\":\"x\",\"action\":\"NONE\",\"hw_degradation\":\"NONE\"," +
                "\"future_agent_field\":42}}";
        MlResponse mapped = mapper.readValue(json, MlResponse.class);
        assertThat(mapped.getOverallSeverity()).isEqualTo("NORMAL");
        assertThat(mapped.getAgent().getJudgment()).isEqualTo("NORMAL");
    }
}
