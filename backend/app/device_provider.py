"""Hardware-neutral contracts. Physical command transports remain deliberately unimplemented."""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CaptureCapabilities:
    audio_transfer: bool = True
    remote_controls: bool = False
    recording_indicator: bool = False
    battery_reporting: bool = False


class DeviceProvider(Protocol):
    capabilities: CaptureCapabilities
    def validate_command(self, action: str) -> None: ...


class TransferOnlyProvider:
    capabilities = CaptureCapabilities()
    def validate_command(self, action: str) -> None:
        raise NotImplementedError('The physical transport, recording controls and indicator are unverified.')


class SimulatedDeviceProvider:
    """Software session transitions only. Never generates audio, battery values or health readings."""
    capabilities = CaptureCapabilities(remote_controls=True)
    def validate_command(self, action: str) -> None:
        if action not in {'ready','start','pause','resume','interrupt','stop','cancel'}:
            raise ValueError('Unsupported simulated command')
