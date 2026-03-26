import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Growth_chart from './icons/Growth_chart.tsx'
import Information_symbol from './icons/Information_symbol.tsx'
import Map_pin from './icons/Map_pin.tsx'
import Growth_chart1 from './icons/Growth_chart1.tsx'
import Megaphone_loudspeaker from './icons/Megaphone_loudspeaker.tsx'
import Document_file_with_folded_corner from './icons/Document_file_with_folded_corner.tsx'
import CategoryButton from './CategoryButton.tsx'


// Component

        function MarketplaceCategories() {
            return (
                <ul className={"marketplaceDetailCategories_inlineLinks__J_xGV"}>
                    <CategoryItem icon={<Information_symbol />} label="Forms" />
                    <CategoryItem icon={<Map_pin />} label="Customer Journey" />
                    <CategoryItem icon={<Growth_chart1 />} label="Work" />
                    <CategoryItem icon={<Megaphone_loudspeaker />} label="Marketing" />
                    <CategoryItem icon={<Document_file_with_folded_corner />} label="Docs" />
                </ul>
            );
        }
    

// Subcomponents

        function CategoryItem({
            icon,
            label
        }: {
            icon: JSX.Element;
            label: string;
        }) {
            return (
                <li>
                    <CategoryButton icon={icon} label={label} />
                </li>
            );
        }
    

export default MarketplaceCategories
