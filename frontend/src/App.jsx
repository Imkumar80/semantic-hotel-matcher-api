import React, { useState, useEffect, useRef } from 'react';
import { cn } from './lib/utils';
import { Search, MapPin, Star, ShieldCheck, Users, Bed, Eye, Info } from 'lucide-react';

function GridBackground({ children }) {
  return (
    <div className="relative flex h-screen w-full flex-col bg-white dark:bg-black overflow-hidden dark text-white">
      <div
        className={cn(
          "fixed inset-0 z-0",
          "[background-size:40px_40px]",
          "[background-image:linear-gradient(to_right,#e4e4e7_1px,transparent_1px),linear-gradient(to_bottom,#e4e4e7_1px,transparent_1px)]",
          "dark:[background-image:linear-gradient(to_right,#262626_1px,transparent_1px),linear-gradient(to_bottom,#262626_1px,transparent_1px)]",
        )}
      />
      <div className="pointer-events-none fixed inset-0 z-0 flex items-center justify-center bg-white [mask-image:radial-gradient(ellipse_at_center,transparent_20%,black)] dark:bg-black"></div>
      
      {/* Ambient Glows */}
      <div className="fixed top-[-20%] right-[-10%] w-[40rem] h-[40rem] rounded-full bg-blue-500/20 blur-[100px] z-0 pointer-events-none"></div>
      <div className="fixed bottom-[-20%] left-[-10%] w-[40rem] h-[40rem] rounded-full bg-purple-500/20 blur-[100px] z-0 pointer-events-none"></div>
      
      <div className="relative z-10 flex flex-col w-full h-full">
        {children}
      </div>
    </div>
  );
}

export default function App() {
  const [query, setQuery] = useState('');
  const [hotels, setHotels] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [hotelDetails, setHotelDetails] = useState(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    const delayDebounce = setTimeout(() => {
      fetchHotels(query);
    }, 300);
    return () => clearTimeout(delayDebounce);
  }, [query]);

  const fetchHotels = async (q) => {
    setLoadingList(true);
    try {
      // Use relative path since it will be served by FastAPI
      const res = await fetch(`/hotels?search=${encodeURIComponent(q)}&size=50`);
      if (res.ok) {
        const data = await res.json();
        setHotels(data.items || []);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingList(false);
    }
  };

  const fetchHotelDetails = async (id) => {
    setSelectedId(id);
    setLoadingDetails(true);
    try {
      const res = await fetch(`/hotels/${id}`);
      if (res.ok) {
        const data = await res.json();
        setHotelDetails(data);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingDetails(false);
    }
  };

  return (
    <GridBackground>
      <nav className="w-full px-8 py-4 border-b border-white/10 bg-black/40 backdrop-blur-md flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center font-bold text-white shadow-lg shadow-blue-500/20">
            A
          </div>
          <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
            Away <span className="text-blue-400 font-semibold">Canonical</span>
          </h1>
        </div>
        <div className="px-4 py-1.5 rounded-full border border-white/10 bg-white/5 text-xs text-gray-300 font-medium">
          AI Entity Resolution Engine
        </div>
      </nav>

      <div className="flex-1 max-w-[1600px] mx-auto w-full p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 h-[calc(100vh-80px)]">
        
        {/* Sidebar */}
        <div className="lg:col-span-4 flex flex-col bg-black/60 backdrop-blur-xl border border-white/10 rounded-3xl overflow-hidden shadow-2xl min-h-0">
          <div className="p-5 border-b border-white/10">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input 
                type="text" 
                placeholder="Search hotels, cities..."
                className="w-full bg-white/5 border border-white/10 rounded-2xl py-3 pl-12 pr-4 text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 transition-all"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
            {loadingList ? (
              <div className="flex items-center justify-center h-40">
                <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
              </div>
            ) : hotels.length === 0 ? (
              <div className="text-center text-gray-500 p-8">No canonical matches found.</div>
            ) : (
              hotels.map(h => (
                <div 
                  key={h.id}
                  onClick={() => fetchHotelDetails(h.id)}
                  className={cn(
                    "p-4 rounded-2xl border transition-all cursor-pointer group hover:bg-white/5",
                    selectedId === h.id 
                      ? "bg-blue-500/10 border-blue-500/30 shadow-[0_0_15px_rgba(59,130,246,0.15)]" 
                      : "bg-transparent border-transparent"
                  )}
                >
                  <h3 className="font-semibold text-gray-100 group-hover:text-white transition-colors line-clamp-1">{h.name || 'Unknown'}</h3>
                  <p className="text-sm text-gray-500 line-clamp-1 mt-1">{h.address}</p>
                  <div className="flex items-center gap-3 mt-3">
                    <span className="flex items-center text-yellow-500 text-xs gap-1">
                      <Star className="w-3.5 h-3.5 fill-current" /> 
                      {h.stars && !isNaN(Number(h.stars)) ? Math.round(Number(h.stars)) : 'N/A'}
                    </span>
                    <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium flex items-center gap-1">
                      <ShieldCheck className="w-3 h-3" />
                      {(h.confidence * 100).toFixed(0)}% Match
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Main Content */}
        <div className="lg:col-span-8 bg-black/60 backdrop-blur-xl border border-white/10 rounded-3xl overflow-hidden shadow-2xl flex flex-col relative min-h-0">
          {loadingDetails ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-8 h-8 border-2 border-purple-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : !hotelDetails ? (
            <div className="flex flex-col items-center justify-center h-full text-gray-500 p-8 text-center">
              <ShieldCheck className="w-16 h-16 mb-4 text-gray-700" />
              <h2 className="text-2xl font-semibold text-gray-300">Select a Canonical Hotel</h2>
              <p className="mt-2 max-w-md">Browse the AI-merged canonical records to see aligned room inventory across suppliers.</p>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto custom-scrollbar">
              {/* Header */}
              <div className="p-8 border-b border-white/10">
                <div className="flex justify-between items-start gap-4">
                  <div>
                    <h2 className="text-3xl font-bold text-white mb-2">{hotelDetails.name}</h2>
                    <p className="flex items-center text-gray-400 gap-2 mb-4">
                      <MapPin className="w-4 h-4" /> {hotelDetails.address}
                    </p>
                    <div className="flex gap-4">
                      <div className="flex items-center text-yellow-500">
                        {[...Array(Math.max(0, Math.round(Number(hotelDetails.stars) || 0)))].map((_, i) => (
                          <Star key={i} className="w-5 h-5 fill-current" />
                        ))}
                      </div>
                      <div className="px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-sm font-medium">
                        Canonical Confidence: {(hotelDetails.confidence * 100).toFixed(1)}%
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2 text-right">
                    <span className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-gray-400 font-mono">
                      A: {hotelDetails.source_a_id || 'N/A'}
                    </span>
                    <span className="px-3 py-1.5 rounded-lg bg-white/5 border border-white/10 text-xs text-gray-400 font-mono">
                      B: {hotelDetails.source_b_id || 'N/A'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Images */}
              {hotelDetails.image_urls?.length > 0 && (
                <div className="p-8 pb-4">
                  <div className="flex gap-4 overflow-x-auto pb-4 custom-scrollbar snap-x">
                    {hotelDetails.image_urls.map((url, i) => (
                      <img 
                        key={i} 
                        src={url} 
                        className="h-64 w-[400px] object-cover rounded-2xl border border-white/10 snap-start shrink-0" 
                        alt="Hotel" 
                        onError={(e) => e.target.style.display = 'none'}
                      />
                    ))}
                  </div>
                </div>
              )}

              {/* Amenities */}
              {hotelDetails.amenities?.length > 0 && (
                <div className="px-8 py-4">
                  <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Canonical Amenities</h3>
                  <div className="flex flex-wrap gap-2">
                    {hotelDetails.amenities.map((am, i) => (
                      <span key={i} className="px-3 py-1.5 rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-300 text-sm">
                        {am}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Aligned Rooms */}
              <div className="p-8 pt-6 mt-4 border-t border-white/10 bg-black/20">
                <h3 className="text-2xl font-semibold text-white mb-2">Aligned Room Inventory</h3>
                <p className="text-gray-400 mb-8">AI-resolved rooms from multiple suppliers into normalized canonical options.</p>

                {(!hotelDetails.matched_rooms || hotelDetails.matched_rooms.length === 0) ? (
                  <div className="p-8 rounded-2xl border border-dashed border-white/20 text-center bg-white/5">
                    <Info className="w-8 h-8 text-gray-500 mx-auto mb-3" />
                    <p className="text-gray-400">No aligned room inventory available.</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {hotelDetails.matched_rooms.map((rm, i) => {
                      const bestName = rm.room_a?.name || rm.room_b?.name || 'Standard Room';
                      const cap = rm.room_a?.capacity || rm.room_b?.capacity || '-';
                      const bed = rm.room_a?.bed_type || rm.room_b?.bed_type || 'Standard Bed';
                      const view = rm.room_a?.view || rm.room_b?.view || 'Standard View';
                      
                      const features = Array.from(new Set([...(rm.room_a?.features || []), ...(rm.room_b?.features || [])])).slice(0,3);

                      return (
                        <div key={i} className="rounded-2xl border border-white/10 bg-white/5 overflow-hidden hover:bg-white/10 hover:border-purple-500/30 transition-all group">
                          <div className="p-6 relative">
                            <div className="absolute top-4 right-4 px-2.5 py-1 bg-purple-500/10 border border-purple-500/20 rounded-full text-purple-400 text-xs font-bold">
                              {(rm.score * 100).toFixed(0)}% Match
                            </div>
                            <h4 className="text-lg font-semibold text-white mb-4 pr-16">{bestName}</h4>
                            
                            <div className="grid grid-cols-2 gap-4 mb-6">
                              <div className="flex items-center gap-2 text-sm text-gray-300">
                                <Users className="w-4 h-4 text-gray-500" /> {cap} Guests
                              </div>
                              <div className="flex items-center gap-2 text-sm text-gray-300">
                                <Bed className="w-4 h-4 text-gray-500" /> {bed}
                              </div>
                              <div className="flex items-center gap-2 text-sm text-gray-300">
                                <Eye className="w-4 h-4 text-gray-500" /> {view}
                              </div>
                            </div>
                            
                            {features.length > 0 && (
                              <div className="flex flex-wrap gap-2 mb-6">
                                {features.map((f, idx) => (
                                  <span key={idx} className="px-2 py-1 rounded-md bg-white/5 border border-white/10 text-xs text-gray-400">
                                    {f}
                                  </span>
                                ))}
                              </div>
                            )}

                            <div className="space-y-2 p-4 rounded-xl bg-black/40 border border-white/5">
                              <div className="flex justify-between items-center text-sm">
                                <span className="text-gray-500">Supplier A</span>
                                <span className="text-gray-300 truncate ml-4" title={rm.room_a?.name}>{rm.room_a?.name || 'N/A'}</span>
                              </div>
                              <div className="flex justify-between items-center text-sm">
                                <span className="text-gray-500">Supplier B</span>
                                <span className="text-gray-300 truncate ml-4" title={rm.room_b?.name}>{rm.room_b?.name || 'N/A'}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>

              {/* Near Misses */}
              {hotelDetails.near_misses?.length > 0 && (
                <div className="p-8 pt-6 mt-4 border-t border-white/10 bg-black/40">
                  <h3 className="text-2xl font-semibold text-white mb-2">Near Misses</h3>
                  <p className="text-gray-400 mb-6">Candidates evaluated but rejected by the AI resolution engine.</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {hotelDetails.near_misses.map((miss, i) => (
                      <div key={i} className="flex justify-between items-center p-4 rounded-xl border border-red-500/20 bg-red-500/5 hover:bg-red-500/10 transition-colors">
                        <div className="flex items-center gap-2">
                          <span className="text-red-400 font-mono text-sm">ID: {miss.miss_id}</span>
                        </div>
                        <span className="px-2.5 py-1 rounded-md bg-red-500/10 text-red-400 text-xs font-medium border border-red-500/20">
                          {(miss.score * 100).toFixed(1)}% Match
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

            </div>
          )}
        </div>
      </div>
      
      <style>{`
        .custom-scrollbar::-webkit-scrollbar { width: 6px; height: 6px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }
      `}</style>
    </GridBackground>
  );
}
