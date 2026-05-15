package com.lab.monitor.dto;

import com.lab.monitor.entity.AiJudgmentHistory;
import org.junit.jupiter.api.Test;

import java.time.OffsetDateTime;

import static org.assertj.core.api.Assertions.assertThat;

class AiJudgmentResponseTest {

    @Test
    void from_copies_all_spec_columns() {
        OffsetDateTime ts = OffsetDateTime.now();
        AiJudgmentHistory e = AiJudgmentHistory.builder()
                .id(7L)
                .pcId("pc-1")
                .judgedAt(ts)
                .anomalyId(42L)
                .judgment("ANOMALY")
                .severity("HIGH")
                .reason("cpu spike")
                .action("ESCALATE")
                .isMock(false)
                .modelName("claude-sonnet")
                .build();

        AiJudgmentResponse r = AiJudgmentResponse.from(e);

        assertThat(r.getId()).isEqualTo(7L);
        assertThat(r.getPcId()).isEqualTo("pc-1");
        assertThat(r.getJudgedAt()).isEqualTo(ts);
        assertThat(r.getAnomalyId()).isEqualTo(42L);
        assertThat(r.getJudgment()).isEqualTo("ANOMALY");
        assertThat(r.getSeverity()).isEqualTo("HIGH");
        assertThat(r.getReason()).isEqualTo("cpu spike");
        assertThat(r.getAction()).isEqualTo("ESCALATE");
        assertThat(r.getIsMock()).isFalse();
        assertThat(r.getModelName()).isEqualTo("claude-sonnet");
    }

    @Test
    void from_tolerates_nullable_columns() {
        AiJudgmentHistory e = AiJudgmentHistory.builder()
                .id(1L).pcId("pc-x").judgedAt(OffsetDateTime.now())
                .build();
        AiJudgmentResponse r = AiJudgmentResponse.from(e);
        assertThat(r.getJudgment()).isNull();
        assertThat(r.getSeverity()).isNull();
        assertThat(r.getIsMock()).isNull();
    }
}
