package com.lab.monitor.service;

import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.dto.MlResponse;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Forwards each accepted metrics payload to the FastAPI ML server and
 * records the response shape (or its absence) as Micrometer counters.
 *
 * <h2>F2-light contract behaviour</h2>
 *
 * <p>The ML server's Pydantic {@code MetricsRequest} declares several
 * fields as required (cpu_percent, memory_percent, disk_*, inbound_mb,
 * outbound_mb). The Spring DTO leaves them nullable so that DB ingestion
 * never refuses a partial payload — a deliberate forward-compatibility
 * decision. The trade-off used to be that any missing required field
 * caused a silent 422 at the ML server, which Spring then swallowed.
 *
 * <p>This service now <b>short-circuits the forward</b> when known-
 * required fields are null, logs the missing field, and bumps a
 * counter <code>rada.ml.forward.skipped{reason=missing_field,
 * field=&lt;name&gt;}</code>. The original payload still lives in
 * {@code metrics_history}; only the ML stage is skipped.
 *
 * <p>HTTP failures are tagged by status — counter
 * <code>rada.ml.forward.failed{status=&lt;code&gt;}</code> — so silent
 * 422 drops become observable in Grafana once F1 exposes
 * {@code /actuator/metrics}.
 *
 * <p>Responses that pass HTTP but lack {@code overall_severity} produce
 * <code>rada.ml.response.invalid{reason=missing_severity}</code>. The
 * actual storage decision still belongs to {@link AlertService}.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class MlForwardService {

    /** Fields the ML Pydantic model marks as required. */
    private static final String[] REQUIRED_FIELDS = {
            "timestamp", "cpu_percent", "memory_percent",
            "disk_read_mb", "disk_write_mb", "inbound_mb", "outbound_mb"
    };

    @Qualifier("mlWebClient")
    private final WebClient mlWebClient;
    private final AlertService alertService;
    private final MeterRegistry meterRegistry;

    public Optional<MlResponse> forward(String pcId, MetricsRequest req) {
        // 1) Required-field check. Skip the ML stage rather than spending
        //    a network round-trip on a payload we know will 422.
        List<String> missing = listMissingRequired(req);
        if (!missing.isEmpty()) {
            for (String field : missing) {
                meterRegistry.counter(
                        "rada.ml.forward.skipped",
                        "reason", "missing_field",
                        "field", field
                ).increment();
            }
            log.warn("ML forward skipped pcId={} missing={}", pcId, missing);
            return Optional.empty();
        }

        try {
            if (req.getPcId() == null) {
                req.setPcId(pcId);
            } else if (!req.getPcId().equals(pcId)) {
                log.warn("pcId mismatch: path={} body={}, keeping body value", pcId, req.getPcId());
            }
            MlResponse resp = mlWebClient.post()
                    .uri("/analyze")
                    .bodyValue(req)
                    .retrieve()
                    .bodyToMono(MlResponse.class)
                    .block();

            // 2) Response-shape check. The ML server may return 200 but
            //    omit overall_severity if a downstream component fails.
            //    Bump an invalid-response counter so the silent skip in
            //    AlertService.handle() is observable.
            if (resp != null && resp.getOverallSeverity() == null) {
                meterRegistry.counter(
                        "rada.ml.response.invalid",
                        "reason", "missing_severity"
                ).increment();
                log.warn("ML response missing overall_severity pcId={}", pcId);
            }
            return Optional.ofNullable(resp);
        } catch (WebClientResponseException e) {
            meterRegistry.counter(
                    "rada.ml.forward.failed",
                    "status", String.valueOf(e.getStatusCode().value())
            ).increment();
            log.warn("ML forward failed pcId={} status={} body={}",
                     pcId, e.getStatusCode(), e.getResponseBodyAsString());
            return Optional.empty();
        } catch (Exception e) {
            // network / timeout / serialization / etc. Bucket as "transport".
            meterRegistry.counter(
                    "rada.ml.forward.failed",
                    "status", "transport"
            ).increment();
            log.warn("ML forward failed pcId={} err={}", pcId, e.getMessage());
            return Optional.empty();
        }
    }

    private static List<String> listMissingRequired(MetricsRequest req) {
        List<String> missing = new ArrayList<>();
        if (req.getTimestamp()   == null) missing.add("timestamp");
        if (req.getCpuPercent()  == null) missing.add("cpu_percent");
        if (req.getMemoryPercent() == null) missing.add("memory_percent");
        if (req.getDiskReadMb()  == null) missing.add("disk_read_mb");
        if (req.getDiskWriteMb() == null) missing.add("disk_write_mb");
        if (req.getInboundMb()   == null) missing.add("inbound_mb");
        if (req.getOutboundMb()  == null) missing.add("outbound_mb");
        return missing;
    }

    @Async("mlExecutor")
    public void forwardAsync(String pcId, MetricsRequest req) {
        try {
            Optional<MlResponse> resp = forward(pcId, req);
            resp.ifPresent(r -> alertService.handle(r, pcId));
        } catch (Exception e) {
            log.warn("Async ML forward error pcId={} err={}", pcId, e.getMessage());
        }
    }
}
