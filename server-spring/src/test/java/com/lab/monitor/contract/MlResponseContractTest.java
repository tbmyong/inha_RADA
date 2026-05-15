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
