package com.lab.monitor.repository;

import com.lab.monitor.entity.MetricsHistory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.OffsetDateTime;

@Repository
public interface MetricsRepository extends JpaRepository<MetricsHistory, Long> {
    Page<MetricsHistory> findByPcIdAndCollectedAtBetween(
            String pcId, OffsetDateTime from, OffsetDateTime to, Pageable pageable);
}
