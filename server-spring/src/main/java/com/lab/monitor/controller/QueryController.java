package com.lab.monitor.controller;

import com.lab.monitor.dto.AiJudgmentResponse;
import com.lab.monitor.dto.AlertResponse;
import com.lab.monitor.entity.AiJudgmentHistory;
import com.lab.monitor.entity.MetricsHistory;
import com.lab.monitor.repository.AiJudgmentRepository;
import com.lab.monitor.repository.AlertRepository;
import com.lab.monitor.repository.MetricsRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.*;

import java.time.OffsetDateTime;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class QueryController {

    private final MetricsRepository metricsRepository;
    private final AlertRepository alertRepository;
    private final AiJudgmentRepository aiJudgmentRepository;

    @GetMapping("/history")
    public Page<MetricsHistory> history(
            @RequestParam String pcId,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to,
            Pageable pageable) {
        return metricsRepository.findByPcIdAndCollectedAtBetween(pcId, from, to, pageable);
    }

    @GetMapping("/alerts")
    public Page<AlertResponse> alerts(
            @RequestParam(required = false) String severity,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to,
            Pageable pageable) {
        var page = (severity == null || severity.isBlank())
                ? alertRepository.findByDetectedAtBetween(from, to, pageable)
                : alertRepository.findBySeverityAndDetectedAtBetween(severity, from, to, pageable);
        return page.map(AlertResponse::from);
    }

    @GetMapping("/ai-judgments")
    public Page<AiJudgmentResponse> aiJudgments(
            @RequestParam(required = false) String pcId,
            @RequestParam(required = false) String severity,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime from,
            @RequestParam @DateTimeFormat(iso = DateTimeFormat.ISO.DATE_TIME) OffsetDateTime to,
            @PageableDefault(size = 20, sort = "judgedAt", direction = Sort.Direction.DESC) Pageable pageable) {
        boolean hasPc = pcId != null && !pcId.isBlank();
        boolean hasSev = severity != null && !severity.isBlank();
        Page<AiJudgmentHistory> page;
        if (hasPc && hasSev) {
            page = aiJudgmentRepository.findByPcIdAndSeverityAndJudgedAtBetween(pcId, severity, from, to, pageable);
        } else if (hasPc) {
            page = aiJudgmentRepository.findByPcIdAndJudgedAtBetween(pcId, from, to, pageable);
        } else if (hasSev) {
            page = aiJudgmentRepository.findBySeverityAndJudgedAtBetween(severity, from, to, pageable);
        } else {
            page = aiJudgmentRepository.findByJudgedAtBetween(from, to, pageable);
        }
        return page.map(AiJudgmentResponse::from);
    }
}
