package com.lab.monitor.dto;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Verifies the agent block (post-realignment) serializes hw_degradation as a String
 * categorical (NONE / SUSPECTED / CONFIRMED) and preserves snake_case keys.
 */
class AgentJudgmentDtoTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void deserialize_hw_degradation_NONE_as_string() throws Exception {
        String json = "{\"judgment\":\"NORMAL\",\"severity\":\"LOW\"," +
                "\"reason\":\"ok\",\"action\":\"NONE\",\"hw_degradation\":\"NONE\"}";
        AgentJudgmentDto dto = mapper.readValue(json, AgentJudgmentDto.class);
        assertThat(dto.getHwDegradation()).isEqualTo("NONE");
    }

    @Test
    void deserialize_hw_degradation_SUSPECTED_as_string() throws Exception {
        String json = "{\"judgment\":\"OBSERVE\",\"severity\":\"LOW\"," +
                "\"hw_degradation\":\"SUSPECTED\"}";
        AgentJudgmentDto dto = mapper.readValue(json, AgentJudgmentDto.class);
        assertThat(dto.getHwDegradation()).isEqualTo("SUSPECTED");
    }

    @Test
    void deserialize_hw_degradation_CONFIRMED_as_string() throws Exception {
        String json = "{\"judgment\":\"ANOMALY\",\"severity\":\"HIGH\"," +
                "\"hw_degradation\":\"CONFIRMED\"}";
        AgentJudgmentDto dto = mapper.readValue(json, AgentJudgmentDto.class);
        assertThat(dto.getHwDegradation()).isEqualTo("CONFIRMED");
    }

    @Test
    void serialize_uses_snake_case_keys_for_hw_degradation_and_is_mock() throws Exception {
        AgentJudgmentDto dto = AgentJudgmentDto.builder()
                .judgment("ANOMALY")
                .severity("HIGH")
                .reason("r")
                .action("ESCALATE")
                .hwDegradation("CONFIRMED")
                .isMock(false)
                .modelName("claude-sonnet-4")
                .build();
        String json = mapper.writeValueAsString(dto);
        assertThat(json).contains("\"hw_degradation\":\"CONFIRMED\"");
        assertThat(json).contains("\"is_mock\":false");
        assertThat(json).contains("\"model_name\":\"claude-sonnet-4\"");
        assertThat(json).doesNotContain("hwDegradation");
        assertThat(json).doesNotContain("isMock");
    }
}
