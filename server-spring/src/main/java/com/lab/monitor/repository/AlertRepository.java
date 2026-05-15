package com.lab.monitor.repository;

import com.lab.monitor.entity.AnomalyHistory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.OffsetDateTime;

@Repository
public interface AlertRepository extends JpaRepository<AnomalyHistory, Long> {
    Page<AnomalyHistory> findBySeverityAndDetectedAtBetween(
            String severity, OffsetDateTime from, OffsetDateTime to, Pageable pageable);

    Page<AnomalyHistory> findByDetectedAtBetween(
            OffsetDateTime from, OffsetDateTime to, Pageable pageable);
}
