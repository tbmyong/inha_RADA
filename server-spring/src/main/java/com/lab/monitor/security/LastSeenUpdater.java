package com.lab.monitor.security;

import com.lab.monitor.repository.AgentAuthRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;

/**
 * Off-thread last_seen_at writer. Kept separate from the filter so the
 * filter's hot path is unaffected; uses the existing mlExecutor pool.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class LastSeenUpdater {

    private final AgentAuthRepository agentAuthRepository;

    @Async("mlExecutor")
    @Transactional
    public void updateAsync(String pcId, OffsetDateTime ts) {
        try {
            agentAuthRepository.updateLastSeen(pcId, ts);
        } catch (RuntimeException e) {
            log.warn("last_seen_at update failed pcId={} err={}", pcId, e.toString());
        }
    }
}
