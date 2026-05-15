package com.lab.monitor.repository;

import com.lab.monitor.entity.PcInfo;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.time.OffsetDateTime;
import java.util.Optional;

@Repository
public interface AgentAuthRepository extends JpaRepository<PcInfo, String> {
    Optional<PcInfo> findByApiKey(String apiKey);

    @Modifying
    @Query("UPDATE PcInfo p SET p.lastSeenAt = :ts WHERE p.pcId = :pcId")
    int updateLastSeen(@Param("pcId") String pcId, @Param("ts") OffsetDateTime ts);
}
