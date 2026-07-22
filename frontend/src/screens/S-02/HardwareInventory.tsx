// Hardware inventory view (FR-GUI-112, 02 §2.1). Lists the USB-CAN adapters and
// their fixed udev channel names (WP-0B-05) as the backend enumerated them. It is
// a read-only window onto backend-detected hardware; it discovers nothing itself.

import type { HardwareAdapter } from "./connectionSource";

interface HardwareInventoryProps {
  adapters: readonly HardwareAdapter[];
}

export function HardwareInventory({ adapters }: HardwareInventoryProps) {
  return (
    <section
      className="oa-s02-hw"
      aria-labelledby="oa-s02-hw-title"
      data-panel="hardware"
    >
      <h2 id="oa-s02-hw-title" className="oa-s02__panel-title">
        하드웨어 인벤토리
      </h2>

      {adapters.length === 0 ? (
        <p role="status">어댑터가 감지되지 않았습니다.</p>
      ) : (
        <table className="oa-s02-hw__table">
          <thead>
            <tr>
              <th scope="col">udev 이름</th>
              <th scope="col">인터페이스</th>
              <th scope="col">드라이버</th>
              <th scope="col">펌웨어</th>
            </tr>
          </thead>
          <tbody>
            {adapters.map((adapter) => (
              <tr key={adapter.id} data-adapter={adapter.udevName}>
                <td>{adapter.udevName}</td>
                <td>{adapter.iface}</td>
                <td>{adapter.driver}</td>
                <td>{adapter.firmware}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
