package com.lab.monitor.entity;

import jakarta.persistence.*;
import lombok.*;
import java.time.OffsetDateTime;

@Entity
@Table(name = "pc_info")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class PcInfo {

    @Id
    @Column(name = "pc_id", length = 64)
    private String pcId;

    @Column(name = "hostname", length = 128)
    private String hostname;

    @Column(name = "api_key", length = 128, unique = true)
    private String apiKey;

    @Column(name = "is_active")
    private Boolean isActive;

    @Column(name = "registered_at")
    private OffsetDateTime registeredAt;

    @Column(name = "last_seen_at")
    private OffsetDateTime lastSeenAt;

    @Column(name = "location", length = 128)
    private String location;

    @Column(name = "gpu_available")
    private Boolean gpuAvailable;
}
