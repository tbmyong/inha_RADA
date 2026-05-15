package com.lab.monitor.controller;

import com.lab.monitor.dto.AiJudgmentResponse;
import com.lab.monitor.entity.AiJudgmentHistory;
import com.lab.monitor.repository.AiJudgmentRepository;
import com.lab.monitor.repository.AlertRepository;
import com.lab.monitor.repository.MetricsRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;

import java.time.OffsetDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class QueryControllerAiJudgmentsTest {

    private AiJudgmentRepository aiRepo;
    private QueryController controller;

    private final OffsetDateTime from = OffsetDateTime.parse("2025-01-01T00:00:00Z");
    private final OffsetDateTime to   = OffsetDateTime.parse("2025-01-02T00:00:00Z");

    @BeforeEach
    void setUp() {
        aiRepo = mock(AiJudgmentRepository.class);
        controller = new QueryController(
                mock(MetricsRepository.class),
                mock(AlertRepository.class),
                aiRepo);
    }

    private Page<AiJudgmentHistory> singletonPage() {
        return new PageImpl<>(List.of(
                AiJudgmentHistory.builder()
                        .id(1L).pcId("pc-1").judgedAt(OffsetDateTime.now())
                        .judgment("ANOMALY").severity("HIGH")
                        .reason("r").action("a").isMock(false).build()));
    }

    @Test
    void neither_filter_calls_findByJudgedAtBetween() {
        when(aiRepo.findByJudgedAtBetween(eq(from), eq(to), any(Pageable.class)))
                .thenReturn(singletonPage());

        Page<AiJudgmentResponse> result =
                controller.aiJudgments(null, null, from, to, PageRequest.of(0, 20));

        verify(aiRepo).findByJudgedAtBetween(eq(from), eq(to), any());
        verify(aiRepo, never()).findByPcIdAndJudgedAtBetween(any(), any(), any(), any());
        verify(aiRepo, never()).findBySeverityAndJudgedAtBetween(any(), any(), any(), any());
        verify(aiRepo, never()).findByPcIdAndSeverityAndJudgedAtBetween(any(), any(), any(), any(), any());
        assertThat(result.getContent()).hasSize(1);
        assertThat(result.getContent().get(0).getJudgment()).isEqualTo("ANOMALY");
    }

    @Test
    void pcId_only_calls_findByPcIdAndJudgedAtBetween() {
        when(aiRepo.findByPcIdAndJudgedAtBetween(eq("pc-1"), eq(from), eq(to), any()))
                .thenReturn(singletonPage());

        controller.aiJudgments("pc-1", null, from, to, PageRequest.of(0, 20));

        verify(aiRepo).findByPcIdAndJudgedAtBetween(eq("pc-1"), eq(from), eq(to), any());
        verify(aiRepo, never()).findByJudgedAtBetween(any(), any(), any());
    }

    @Test
    void severity_only_calls_findBySeverityAndJudgedAtBetween() {
        when(aiRepo.findBySeverityAndJudgedAtBetween(eq("HIGH"), eq(from), eq(to), any()))
                .thenReturn(singletonPage());

        controller.aiJudgments(null, "HIGH", from, to, PageRequest.of(0, 20));

        verify(aiRepo).findBySeverityAndJudgedAtBetween(eq("HIGH"), eq(from), eq(to), any());
    }

    @Test
    void both_filters_call_findByPcIdAndSeverityAndJudgedAtBetween() {
        when(aiRepo.findByPcIdAndSeverityAndJudgedAtBetween(
                eq("pc-1"), eq("HIGH"), eq(from), eq(to), any()))
                .thenReturn(singletonPage());

        controller.aiJudgments("pc-1", "HIGH", from, to, PageRequest.of(0, 20));

        verify(aiRepo).findByPcIdAndSeverityAndJudgedAtBetween(
                eq("pc-1"), eq("HIGH"), eq(from), eq(to), any());
    }

    @Test
    void blank_filters_treated_as_absent() {
        when(aiRepo.findByJudgedAtBetween(any(), any(), any())).thenReturn(singletonPage());

        controller.aiJudgments("", "  ", from, to, PageRequest.of(0, 20));

        verify(aiRepo).findByJudgedAtBetween(eq(from), eq(to), any());
    }

    @Test
    void pageable_is_forwarded_verbatim() {
        Pageable p = PageRequest.of(2, 7, Sort.by(Sort.Direction.DESC, "judgedAt"));
        when(aiRepo.findByJudgedAtBetween(eq(from), eq(to), eq(p)))
                .thenReturn(new PageImpl<>(List.of(), p, 0));

        controller.aiJudgments(null, null, from, to, p);

        verify(aiRepo).findByJudgedAtBetween(eq(from), eq(to), eq(p));
    }
}
