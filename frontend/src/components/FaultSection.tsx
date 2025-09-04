import React, { useState } from 'react';
import { useEntity } from '@hakit/core';

const FaultSection: React.FC = () => {
  const [openLevels, setOpenLevels] = useState<string[]>([]); // Track multiple opened levels
  const healthEntity = useEntity('sensor.safety_app_health');
  const faultsConfig = healthEntity?.attributes?.configuration?.faults || {};

  const faultEntities = Object.keys(faultsConfig).map(faultKey => `sensor.fault_${faultKey.toLowerCase()}`);

  const faultData = faultEntities.map(entityId => {
    return {
      id: entityId,
      state: (useEntity(entityId) || {}).state || 'Unknown',
      friendlyName: ((useEntity(entityId) || {}).attributes || {}).friendly_name || entityId.replace('sensor.fault_', ''),
      description: ((useEntity(entityId) || {}).attributes || {}).description || '',
      location: ((useEntity(entityId) || {}).attributes || {}).location || '',
      level: ((useEntity(entityId) || {}).attributes || {}).level || 'level_4',
    };
  });

  const groupedFaults = faultData.reduce<Record<string, typeof faultData>>((acc, fault) => {
    if (!acc[fault.level]) acc[fault.level] = [];
    acc[fault.level].push(fault);
    return acc;
  }, {});

  const levelOrder = ['level_1', 'level_2', 'level_3', 'level_4'];
  const levelTitles: Record<string, string> = {
    level_1: 'Immediate Emergency',
    level_2: 'Hazard',
    level_3: 'Warning',
    level_4: 'Notice',
  };

  const levelColors: Record<string, string> = {
    level_1: '#EF4444', // red
    level_2: '#F97316', // orange
    level_3: '#EAB308', // yellow
    level_4: '#3B82F6', // blue
  };

  const toggleLevel = (level: string) => {
    setOpenLevels(prev => (prev.includes(level) ? prev.filter(l => l !== level) : [...prev, level]));
  };

  return (
    <div className='w-full max-w-4xl mx-auto bg-gray-800 shadow-lg rounded-lg overflow-hidden'>
      <div className='p-6 text-gray-100'>
        <h2 className='text-2xl font-bold mb-6'>System Faults</h2>
        <div>
          {levelOrder.map(level => {
            if (!groupedFaults[level]) return null;

            return (
              <div key={level} className='mb-4'>
                <button
                  onClick={() => toggleLevel(level)}
                  className='w-full text-left p-4 bg-gray-700 hover:bg-gray-600 rounded-lg transition-colors duration-200 focus:outline-none'
                >
                  <div className='flex items-center justify-between'>
                    <span className='text-lg font-semibold text-gray-100'>{levelTitles[level]}</span>
                    <span className='bg-gray-600 text-gray-100 px-2 py-1 rounded-full text-sm'>{groupedFaults[level].length}</span>
                  </div>
                </button>
                {openLevels.includes(level) && (
                  <div className='mt-2 space-y-4'>
                    {groupedFaults[level].map((fault, index) => (
                      <div key={index} className='border rounded-lg overflow-hidden bg-gray-700'>
                        <div style={{ backgroundColor: levelColors[fault.level] }} className='text-white p-4'>
                          <h3 className='text-lg font-semibold'>{fault.friendlyName}</h3>
                        </div>
                        <div className='p-4 text-gray-100'>
                          <p className='text-sm mb-2'>{fault.description}</p>
                          <div className='flex justify-between items-center'>
                            <span className='text-sm font-medium'>Location: {fault.location || 'None'}</span>
                            <span
                              style={{ backgroundColor: levelColors[fault.level] }}
                              className='text-white font-bold px-3 py-1 rounded-full text-sm'
                            >
                              {fault.state}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default FaultSection;
