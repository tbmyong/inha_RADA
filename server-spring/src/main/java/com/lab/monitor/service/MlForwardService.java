package com.lab.monitor.service;

import com.lab.monitor.dto.MetricsRequest;
import com.lab.monitor.dto.MlResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.Optional;

@Slf4j
@Service
@RequiredArgsConstructor
public class MlForwardService {

    @Qualifier("mlWebClient")
    private final WebClient mlWebClient;
    private final AlertService alertService;

    public Optional<MlResponse> forward(String pcId, MetricsRequest req) {
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
            return Optional.ofNullable(resp);
        } catch (Exception e) {
            log.warn("ML forward failed pcId={} err={}", pcId, e.getMessage());
            return Optional.empty();
        }
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
