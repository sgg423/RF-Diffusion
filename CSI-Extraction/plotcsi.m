% Copyright (C) 2026 Khandaker Foysal Haque
% contact: haque.k@northeastern.edu
% This program is free software: you can redistribute it and/or modify
% it under the terms of the GNU General Public License as published by
% the Free Software Foundation, either version 3 of the License, or
% (at your option) any later version.
% This program is distributed in the hope that it will be useful,
% but WITHOUT ANY WARRANTY; without even the implied warranty of
% MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
% GNU General Public License for more details.
% You should have received a copy of the GNU General Public License
% along with this program.  If not, see <https://www.gnu.org/licenses/>.

function [] = plotcsi( csi, nfft, normalize )
%PLOTCSI Summary of this function goes here
%   Detailed explanation goes here

csi_buff = fftshift(csi,2);
csi_phase = rad2deg(angle(csi_buff));
for cs = 1:size(csi_buff,1)
    csi = abs(csi_buff(cs,:));
    if normalize
        csi = csi./max(csi);
    end
    csi_buff(cs,:) = csi;
end

figure
x = -(nfft/2):1:(nfft/2-1);
subplot(3,1,3)
imagesc(x,[1 size(csi_buff,1)],csi_buff)
myAxis = axis();
axis([min(x)-0.5, max(x)+0.5, myAxis(3), myAxis(4)])
set(gca,'Ydir','reverse')
xlabel('Subcarrier')
ylabel('Packet number')

max_y = max(csi_buff(:));
for cs = 1:size(csi_buff,1)
    csi = csi_buff(cs,:);
    
    subplot(3,1,1)
    plot(x,csi);
    grid on
    myAxis = axis();
    axis([min(x)-0.5, max(x)+0.5, 0, max_y])
    xlabel('Subcarrier')
    ylabel('Magnitude')
    title('Channel State Information')
    text(max(x),max_y-(0.05*max_y),['Packet #',num2str(cs),' of ',num2str(size(csi_buff,1))],'HorizontalAlignment','right','Color',[0.75 0.75 0.75]);
    
    subplot(3,1,2)
    plot(x,csi_phase(cs,:));
    grid on
    myAxis = axis();
    axis([min(x)-0.5, max(x)+0.5, -180, 180])
    xlabel('Subcarrier')
    ylabel('Phase')
    disp('Press any key to continue..');
    waitforbuttonpress();
end
close

end

