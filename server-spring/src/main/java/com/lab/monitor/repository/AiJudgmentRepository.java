package com.lab.monitor.repository;

import com.lab.monitor.entity.AiJudgmentHistory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.time.OffsetDateTime;

@Repository
public interface AiJudgmentRepository extends JpaRepository<AiJudgmentHistory, Long> {

    Page<AiJudgmentHistory> findByJudgedAtBetween(
            OffsetDateTime from, OffsetDateTime to, Pageable pageable);

    Page<AiJudgmentHistory> findByPcIdAndJudgedAtBetween(
            String pcId, OffsetDateTime from, OffsetDateTime to, Pageable pageable);

    Page<AiJudgmentHistory> findBySeverityAndJudgedAtBetween(
            String severity, OffsetDateTime from, OffsetDateTime to, Pageable pageable);

    Page<AiJudgmentHistory> findByPcIdAndSeverityAndJudgedAtBetween(
            String pcId, String severity, OffsetDateTime from, OffsetDateTime to, Pageable pageable);
}
