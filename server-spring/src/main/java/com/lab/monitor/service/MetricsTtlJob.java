package com.lab.monitor.service;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.annotation.PostConstruct;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Nightly TTL pruner for {@code metrics_history}.
 *
 * Deletes rows older than {@link #RETENTION_DAYS} days in batches of
 * {@link #BATCH_SIZE} to keep transaction time bounded on a hot table.
 * Fires once a day at 03:00 Asia/Seoul (off-peak); the cron string is the
 * 6-field Spring form (sec min hour dom mon dow).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class MetricsTtlJob {

    static final int RETENTION_DAYS = 30;
    static final int BATCH_SIZE = 10_000;
    /** Hard cap on per-run loop iterations to avoid runaway deletes. */
    static final int MAX_BATCHES = 1_000;

    @PersistenceContext
    private EntityManager em;

    private final MeterRegistry meterRegistry;

    private Counter successCounter;
    private Counter failedCounter;
    /** 마지막 prune 실행에서 삭제된 행 수 (gauge). */
    private final AtomicLong lastDeletedCount = new AtomicLong(0L);

    @PostConstruct
    void registerMetrics() {
        this.successCounter = meterRegistry.counter("rada.metrics.ttl.success");
        this.failedCounter  = meterRegistry.counter("rada.metrics.ttl.failed");
        meterRegistry.gauge("rada.metrics.ttl.deleted_count", lastDeletedCount);
    }

    @Scheduled(cron = "0 0 3 * * *", zone = "Asia/Seoul")
    public void prune() {
        OffsetDateTime cutoff = OffsetDateTime.now().minusDays(RETENTION_DAYS);
        long totalDeleted = 0;
        int batches = 0;
        try {
            while (batches < MAX_BATCHES) {
                int deleted = deleteBatch(cutoff);
                if (deleted <= 0) break;
                totalDeleted += deleted;
                batches++;
                if (deleted < BATCH_SIZE) break;
            }
            lastDeletedCount.set(totalDeleted);
            if (successCounter != null) successCounter.increment();
            log.info("metrics_history TTL prune: cutoff={} deleted={} batches={}",
                    cutoff, totalDeleted, batches);
        } catch (Exception e) {
            if (failedCounter != null) failedCounter.increment();
            log.warn("metrics_history TTL prune failed cutoff={} batches={} err={}",
                    cutoff, batches, e.getMessage());
        }
    }

    /**
     * Native-SQL batch delete restricted via subquery to keep the row count
     * per transaction bounded regardless of DB row count.
     * Public-visible for @Transactional proxying.
     */
    @Transactional
    public int deleteBatch(OffsetDateTime cutoff) {
        return em.createNativeQuery(
                        "DELETE FROM metrics_history WHERE id IN ("
                                + "  SELECT id FROM metrics_history"
                                + "  WHERE collected_at < :cutoff"
                                + "  LIMIT :batch"
                                + ")")
                .setParameter("cutoff", cutoff)
                .setParameter("batch", BATCH_SIZE)
                .executeUpdate();
    }
}
